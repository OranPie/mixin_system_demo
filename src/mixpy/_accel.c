/*
 * _accel.c — C extension accelerating mixpy runtime dispatch hot paths.
 *
 * Provides optimised replacements for:
 *   _resolve_path()  → fast_resolve_path()
 *   _eval_when()     → fast_eval_when()  (leaf operators only)
 *   merge_kwargs()   → fast_merge_kwargs()
 *
 * Build:
 *   MIXPY_BUILD_ACCEL=1 python3 setup.py build_ext --inplace
 *
 * Compatible with Python 3.10+ stable C API.
 */

#define PY_SSIZE_T_CLEAN
#include "Python.h"

#include <string.h>
#include <ctype.h>

/* ------------------------------------------------------------------ */
/* fast_resolve_path(ctx_dict, path_str)                              */
/*                                                                    */
/* Resolves a dotted path (with optional [index] notation) against a  */
/* context dict.  Equivalent to the pure-Python _resolve_path() but   */
/* avoids per-call regex compilation.                                 */
/* ------------------------------------------------------------------ */

static PyObject *
accel_fast_resolve_path(PyObject *self, PyObject *args)
{
    PyObject *ctx;
    const char *path;
    Py_ssize_t path_len;

    if (!PyArg_ParseTuple(args, "Os#", &ctx, &path, &path_len))
        return NULL;

    if (!PyDict_Check(ctx)) {
        PyErr_SetString(PyExc_TypeError, "ctx must be a dict");
        return NULL;
    }

    /* Fast path: direct key lookup in the context dict. */
    PyObject *direct = PyDict_GetItemString(ctx, path);
    if (direct) {
        Py_INCREF(direct);
        return direct;
    }

    /* Walk tokens separated by '.' (dots inside [] are not separators). */
    PyObject *cur = ctx;
    Py_INCREF(cur);

    const char *p = path;
    const char *end = path + path_len;

    while (p < end) {
        /* Find the end of the current token (next unbracketed dot or end). */
        const char *tok_start = p;
        int bracket_depth = 0;
        while (p < end) {
            if (*p == '[') bracket_depth++;
            else if (*p == ']') bracket_depth--;
            else if (*p == '.' && bracket_depth == 0) break;
            p++;
        }
        /* tok_start..p is one token, e.g. "kwargs" or "args[0]" */
        Py_ssize_t tok_len = p - tok_start;
        if (p < end && *p == '.') p++;  /* skip the dot */

        if (tok_len == 0) {
            /* empty token → malformed path */
            Py_DECREF(cur);
            Py_RETURN_NONE;
        }

        /* Split token into key and optional integer index.            */
        /* e.g.  "args[0]"  →  key="args", idx_str="0"                */
        const char *bracket = memchr(tok_start, '[', (size_t)tok_len);
        const char *key_start = tok_start;
        Py_ssize_t key_len;
        long idx = -1;
        int has_idx = 0;

        if (bracket) {
            key_len = bracket - tok_start;
            const char *idx_start = bracket + 1;
            const char *idx_end = memchr(idx_start, ']',
                                         (size_t)(tok_start + tok_len - idx_start));
            if (!idx_end) {
                /* Malformed bracket notation */
                Py_DECREF(cur);
                Py_RETURN_NONE;
            }
            /* Parse the integer index */
            char idx_buf[32];
            Py_ssize_t idx_len = idx_end - idx_start;
            if (idx_len <= 0 || idx_len >= (Py_ssize_t)sizeof(idx_buf)) {
                Py_DECREF(cur);
                Py_RETURN_NONE;
            }
            memcpy(idx_buf, idx_start, (size_t)idx_len);
            idx_buf[idx_len] = '\0';
            /* Validate digits */
            for (Py_ssize_t i = 0; i < idx_len; i++) {
                if (!isdigit((unsigned char)idx_buf[i])) {
                    Py_DECREF(cur);
                    Py_RETURN_NONE;
                }
            }
            idx = strtol(idx_buf, NULL, 10);
            has_idx = 1;
        } else {
            key_len = tok_len;
        }

        /* Build a temporary Python str for the key. */
        PyObject *key_obj = PyUnicode_FromStringAndSize(key_start, key_len);
        if (!key_obj) {
            Py_DECREF(cur);
            return NULL;
        }

        /* Lookup: dict → PyDict_GetItem; otherwise → getattr */
        PyObject *next = NULL;
        if (PyDict_Check(cur)) {
            next = PyDict_GetItem(cur, key_obj);  /* borrowed ref */
            Py_XINCREF(next);
        } else {
            next = PyObject_GetAttr(cur, key_obj);
            if (!next) {
                /* getattr failed — return None instead of propagating */
                PyErr_Clear();
            }
        }
        Py_DECREF(key_obj);
        Py_DECREF(cur);

        if (!next) {
            Py_RETURN_NONE;
        }
        cur = next;  /* cur now owns the reference */

        /* Optional index access */
        if (has_idx) {
            PyObject *item = PySequence_GetItem(cur, idx);
            Py_DECREF(cur);
            if (!item) {
                PyErr_Clear();
                Py_RETURN_NONE;
            }
            cur = item;
        }
    }

    return cur;  /* caller owns */
}

/* ------------------------------------------------------------------ */
/* fast_eval_when(left, op_str, right, ctx_dict)                      */
/*                                                                    */
/* Evaluates a single (leaf) When condition.  For AND/OR/NOT the      */
/* caller should fall back to Python recursion.                       */
/* Returns 1 (True) or 0 (False).                                    */
/* ------------------------------------------------------------------ */

static PyObject *
accel_fast_eval_when(PyObject *self, PyObject *args)
{
    const char *left_path;
    const char *op_str;
    PyObject *right;
    PyObject *ctx;

    if (!PyArg_ParseTuple(args, "ssOO", &left_path, &op_str, &right, &ctx))
        return NULL;

    if (!PyDict_Check(ctx)) {
        PyErr_SetString(PyExc_TypeError, "ctx must be a dict");
        return NULL;
    }

    /* Resolve the left-hand value via fast_resolve_path logic. */
    PyObject *resolve_args = Py_BuildValue("(Os)", ctx, left_path);
    if (!resolve_args) return NULL;
    PyObject *left_val = accel_fast_resolve_path(self, resolve_args);
    Py_DECREF(resolve_args);
    if (!left_val) return NULL;

    int result = -1;  /* -1 = not yet determined */

    /* Dispatch on operator string */
    if (strcmp(op_str, "EQ") == 0) {
        result = PyObject_RichCompareBool(left_val, right, Py_EQ);
    }
    else if (strcmp(op_str, "NE") == 0) {
        result = PyObject_RichCompareBool(left_val, right, Py_NE);
    }
    else if (strcmp(op_str, "GT") == 0) {
        result = PyObject_RichCompareBool(left_val, right, Py_GT);
    }
    else if (strcmp(op_str, "LT") == 0) {
        result = PyObject_RichCompareBool(left_val, right, Py_LT);
    }
    else if (strcmp(op_str, "GE") == 0) {
        result = PyObject_RichCompareBool(left_val, right, Py_GE);
    }
    else if (strcmp(op_str, "LE") == 0) {
        result = PyObject_RichCompareBool(left_val, right, Py_LE);
    }
    else if (strcmp(op_str, "IN") == 0) {
        result = PySequence_Contains(right, left_val);
    }
    else if (strcmp(op_str, "NOT_IN") == 0) {
        int r = PySequence_Contains(right, left_val);
        if (r >= 0) result = !r;
        else result = -1;
    }
    else if (strcmp(op_str, "IS_NONE") == 0) {
        result = (left_val == Py_None) ? 1 : 0;
    }
    else if (strcmp(op_str, "NOT_NONE") == 0) {
        result = (left_val != Py_None) ? 1 : 0;
    }
    else if (strcmp(op_str, "LEN_EQ") == 0) {
        Py_ssize_t len = PyObject_Length(left_val);
        if (len < 0) { PyErr_Clear(); result = 0; }
        else {
            long rhs = PyLong_AsLong(right);
            if (rhs == -1 && PyErr_Occurred()) { Py_DECREF(left_val); return NULL; }
            result = (len == rhs) ? 1 : 0;
        }
    }
    else if (strcmp(op_str, "LEN_GT") == 0) {
        Py_ssize_t len = PyObject_Length(left_val);
        if (len < 0) { PyErr_Clear(); result = 0; }
        else {
            long rhs = PyLong_AsLong(right);
            if (rhs == -1 && PyErr_Occurred()) { Py_DECREF(left_val); return NULL; }
            result = (len > rhs) ? 1 : 0;
        }
    }
    else if (strcmp(op_str, "LEN_LT") == 0) {
        Py_ssize_t len = PyObject_Length(left_val);
        if (len < 0) { PyErr_Clear(); result = 0; }
        else {
            long rhs = PyLong_AsLong(right);
            if (rhs == -1 && PyErr_Occurred()) { Py_DECREF(left_val); return NULL; }
            result = (len < rhs) ? 1 : 0;
        }
    }
    else {
        /* Unknown or recursive operator (AND/OR/NOT) — signal caller. */
        Py_DECREF(left_val);
        PyErr_Format(PyExc_ValueError,
                     "Unsupported operator for C fast path: %s", op_str);
        return NULL;
    }

    Py_DECREF(left_val);

    if (result < 0) {
        /* A comparison raised an exception */
        return NULL;
    }

    return PyBool_FromLong(result);
}

/* ------------------------------------------------------------------ */
/* fast_merge_kwargs(*maps)                                           */
/*                                                                    */
/* Merge N dicts into one, raising TypeError on duplicate keys.       */
/* Skips None arguments.                                              */
/* ------------------------------------------------------------------ */

static PyObject *
accel_fast_merge_kwargs(PyObject *self, PyObject *args)
{
    Py_ssize_t n = PyTuple_GET_SIZE(args);

    PyObject *out = PyDict_New();
    if (!out) return NULL;

    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *m = PyTuple_GET_ITEM(args, i);

        if (m == Py_None)
            continue;

        /* Convert to dict if not already one */
        PyObject *d;
        int need_decref = 0;
        if (PyDict_Check(m)) {
            d = m;
        } else {
            d = PyObject_CallOneArg((PyObject *)&PyDict_Type, m);
            if (!d) {
                Py_DECREF(out);
                return NULL;
            }
            need_decref = 1;
        }

        /* Iterate over items */
        PyObject *key, *value;
        Py_ssize_t pos = 0;
        while (PyDict_Next(d, &pos, &key, &value)) {
            /* Check for duplicate keys */
            int exists = PyDict_Contains(out, key);
            if (exists < 0) {
                if (need_decref) Py_DECREF(d);
                Py_DECREF(out);
                return NULL;
            }
            if (exists) {
                PyObject *key_repr = PyObject_Repr(key);
                const char *key_str = key_repr ?
                    PyUnicode_AsUTF8(key_repr) : "?";
                PyErr_Format(PyExc_TypeError,
                             "multiple values for keyword argument %s",
                             key_str);
                Py_XDECREF(key_repr);
                if (need_decref) Py_DECREF(d);
                Py_DECREF(out);
                return NULL;
            }
            if (PyDict_SetItem(out, key, value) < 0) {
                if (need_decref) Py_DECREF(d);
                Py_DECREF(out);
                return NULL;
            }
        }

        if (need_decref) Py_DECREF(d);
    }

    return out;
}

/* ------------------------------------------------------------------ */
/* Module definition                                                  */
/* ------------------------------------------------------------------ */

static PyMethodDef accel_methods[] = {
    {"fast_resolve_path", accel_fast_resolve_path, METH_VARARGS,
     "Resolve a dotted path (with optional [index]) against a context dict."},
    {"fast_eval_when", accel_fast_eval_when, METH_VARARGS,
     "Evaluate a leaf When condition (op as string). "
     "Returns True/False. Raises ValueError for AND/OR/NOT."},
    {"fast_merge_kwargs", accel_fast_merge_kwargs, METH_VARARGS,
     "Merge multiple dicts, raising TypeError on duplicate keys."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef accel_module = {
    PyModuleDef_HEAD_INIT,
    "_accel",
    "C-accelerated hot-path helpers for mixpy runtime dispatch.",
    -1,
    accel_methods
};

PyMODINIT_FUNC
PyInit__accel(void)
{
    return PyModule_Create(&accel_module);
}
