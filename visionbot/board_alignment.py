"""Conservative screen-based correction of a slightly miscalibrated chessboard.

The board is an 8x8 *solid-color* checkerboard. We locate its four outer
edges using its two dominant square colors rather than identifying pieces.
No DOM, browser APIs, site calls, or automation is used here.

We intentionally do not extrapolate from arbitrary screen content. A large
layout change, a theme with a textured board, or an obscured board requires
manual recalibration. Never guess a rectangle used for mouse clicks.
"""
from __future__ import annotations

import numpy as np


class BoardAlignmentError(ValueError):
    pass


def _dominant_colors(region: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Obtain two prominent, different flat square colors from screenshot."""
    pixels = region[:, :, :3].reshape(-1, 3)
    quantized = (pixels.astype(np.uint32) >> 3)
    packed = (quantized[:, 0] << 10) | (quantized[:, 1] << 5) | quantized[:, 2]
    counts = np.bincount(packed, minlength=32768)
    # Only very common colors can be chessboard backgrounds. Interface panels
    # and chess pieces cover much less than 8% of the region each.
    candidates = np.argsort(counts)[-32:][::-1]
    chosen = []
    for code in candidates:
        if counts[code] < 0.07 * len(pixels):
            break
        mask = packed == code
        representative = np.median(pixels[mask], axis=0).astype(np.float32)
        if all(np.linalg.norm(representative - prev) > 45 for prev in chosen):
            chosen.append(representative)
            if len(chosen) == 2:
                break
    if len(chosen) != 2:
        raise BoardAlignmentError('Cannot identify two flat chessboard square colors')
    return chosen[0], chosen[1]


def _longest_run(positions: np.ndarray) -> tuple[int, int]:
    if len(positions) == 0:
        raise BoardAlignmentError('No visible chessboard edge')
    breaks = np.where(np.diff(positions) > 1)[0]
    starts = np.r_[0, breaks + 1]
    ends = np.r_[breaks, len(positions)-1]
    longest = np.argmax(positions[ends] - positions[starts])
    return int(positions[starts[longest]]), int(positions[ends[longest]])


def refine_board_rect(image: np.ndarray, rect: tuple[int, int, int], *,
                      max_shift: int = 25) -> tuple[tuple[int, int, int], dict]:
    """Correct <=25px border drift on a standard solid-color 8x8 board.

    Uses only nearby pixels and fails closed unless the recovered rectangle is
    square and close to the user-selected rectangle. Pixel rect is (x,y,size),
    matching VisionAutoplay and Screen.grab().
    """
    x, y, size = map(int, rect)
    h, w = image.shape[:2]
    if size < 320 or x < 0 or y < 0 or x+size > w or y+size > h:
        raise BoardAlignmentError('Selected board rectangle is outside screenshot')
    # The rectangle is expected to be close already. Approximate colors using
    # the interior, away from surrounding browser UI.
    inner = image[y+int(size*.06):y+int(size*.94),
                  x+int(size*.06):x+int(size*.94), :3]
    if inner.size == 0:
        raise BoardAlignmentError('No board pixels')
    color1, color2 = _dominant_colors(inner)

    pad = max_shift+2
    x0=max(0,x-pad); y0=max(0,y-pad)
    x1=min(w,x+size+pad);y1=min(h,y+size+pad)
    sample=image[y0:y1,x0:x1,:3].astype(np.float32)
    # Solid chessboard background pixels match either palette color. Knight,
    # queen, labels and move highlights are ignored by the aggregate profile.
    good = (np.linalg.norm(sample-color1,axis=2)<17) | (np.linalg.norm(sample-color2,axis=2)<17)
    # Exclude top/bottom strips when locating LEFT/RIGHT edges and vice versa.
    iy0=max(0,y+int(size*.12)-y0)
    iy1=min(y1-y0,y+int(size*.88)-y0)
    ix0=max(0,x+int(size*.12)-x0)
    ix1=min(x1-x0,x+int(size*.88)-x0)
    if iy1-iy0 < 100 or ix1-ix0 < 100:
        raise BoardAlignmentError('Insufficient board background for alignment')
    x_profile=good[iy0:iy1].mean(axis=0)
    y_profile=good[:,ix0:ix1].mean(axis=1)
    # Contiguous central checkerboard should cover >60% per scanline/column,
    # while browser chrome surrounding the board should not match either color.
    # Piece silhouettes can create narrow low-scoring gaps inside the
    # checkerboard (a queen makes a whole column less uniform). The requested
    # rect already constrains the search to the immediate board vicinity, so
    # use the outermost high-confidence pixels, not the longest interior run.
    xc=np.where(x_profile>=.62)[0]+x0
    yc=np.where(y_profile>=.62)[0]+y0
    if len(xc)==0 or len(yc)==0:
        raise BoardAlignmentError('No visible checkerboard borders')
    left,right=int(xc.min()),int(xc.max())
    top,bottom=int(yc.min()),int(yc.max())
    if (float(np.mean(x_profile[left-x0:right-x0+1]>.58))<.70
            or float(np.mean(y_profile[top-y0:bottom-y0+1]>.58))<.70):
        raise BoardAlignmentError('Chessboard continuity insufficient')
    width=right-left+1
    height=bottom-top+1
    if min(width,height)<320 or abs(width-height)>3:
        raise BoardAlignmentError('Chessboard borders are not sufficiently square')
    corrected=int(round((width+height)/2))
    if any(abs(a-b)>max_shift for a,b in ((left,x),(top,y),(right+1,x+size),(bottom+1,y+size))):
        raise BoardAlignmentError('Board layout changed too much; recalibrate manually')
    # Reconfirm that at least 70% of pixels in the new square are a known
    # background color; otherwise the detected area could be another UI pane.
    coverage = float(good[top-y0:bottom+1,left-x0:right+1].mean())
    if coverage < .67:
        raise BoardAlignmentError('Found board region is occluded or not a flat theme')
    return (left,top,corrected), {
        'shift_x': left-x, 'shift_y':top-y, 'delta_size':corrected-size,
        'background_coverage':round(coverage,4)
    }
