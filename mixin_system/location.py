from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .model import At

@dataclass(frozen=True)
class SliceSpec:
    """Limit matches to a region between anchors.

    Either side can be omitted:
      - from_anchor=None -> from function start
      - to_anchor=None   -> to function end
    """
    from_anchor: Optional["At"] = None
    to_anchor: Optional["At"] = None
    include_from: bool = False
    include_to: bool = False

@dataclass(frozen=True)
class NearSpec:
    """Keep matches within max_distance of anchor (measured in *statements*)."""
    anchor: "At"
    max_distance: int = 3

@dataclass(frozen=True)
class AnchorSpec:
    """Pick a match relative to anchor.

    Ordering is based on (statement index, intra-statement order).
    """
    anchor: "At"
    offset: int = 0
    inclusive: bool = False
