import browserbotics as bb
import time
import math
import random


# ═══════════════════════════════════════════════════════════════
#   CITY HOSPITAL — WARD A  (3 Robots × 3 Patients)
#   Robot-1  ARIA  →  Bed-1  (Vitals: BP + Blood + Temp + O2)
#   Robot-2  NOVA  →  Bed-2  (Vitals: BP + ECG + Glucose)
#   Robot-3  ZETA  →  Bed-3  (Vitals: Temp + O2 + Neuro)
#   Layout : large ward, nurses' station, medicine cabinet,
#            reception desk, waiting area, corridor
# ═══════════════════════════════════════════════════════════════

TICK = 0.022

# ── Ward dimensions ──────────────────────────────────────────
WARD_W = 16.0   # x : -8  →  +8
WARD_D = 12.0   # y : -6  →  +6
WARD_H =  3.4

hw = WARD_W / 2    # 8.0
hd = WARD_D / 2    # 6.0

# ── Camera — top-down view ───────────────────────────────────
try:
    bb.resetDebugVisualizerCamera(
        cameraDistance=18.0,
        cameraYaw=0,
        cameraPitch=-72,
        cameraTargetPosition=[0.0, 0.0, 0.0]
    )
except Exception: pass

# ── BED positions (3 beds across the ward) ───────────────────
BED = [
    {"cx": -4.5, "cy":  1.2},   # Bed 1 — left bay
    {"cx":  0.5, "cy":  1.2},   # Bed 2 — centre bay
    {"cx":  5.0, "cy":  1.2},   # Bed 3 — right bay
]

# ── Robot docking stations ────────────────────────────────────
DOCK = [
    {"x": -6.5, "y": -3.5},    # Dock 1 — back-left
    {"x":  0.0, "y": -4.0},    # Dock 2 — back-centre
    {"x":  6.5, "y": -3.5},    # Dock 3 — back-right
]

# ── Medicine trolley positions ────────────────────────────────
CART = [
    {"x": -5.8, "y":  0.6},
    {"x":  0.0, "y":  0.5},
    {"x":  5.8, "y":  0.6},
]

# ── Robot colours (scrubs + accent) ──────────────────────────
ROBOT_CFG = [
    {"name": "ARIA", "scrub": "#4fc3f7", "accent": "#0288d1", "tool": "#ff8a65"},
    {"name": "NOVA", "scrub": "#a5d6a7", "accent": "#388e3c", "tool": "#ffd54f"},
    {"name": "ZETA", "scrub": "#ce93d8", "accent": "#7b1fa2", "tool": "#80cbc4"},
]

# ── Patient colours ───────────────────────────────────────────
PAT_CFG = [
    {"skin": "#f5cba7", "hair": "#5d4037", "gown": "#e3f2fd"},
    {"skin": "#d4a574", "hair": "#2c1810", "gown": "#fce4ec"},
    {"skin": "#fdbcb4", "hair": "#1a1a2e", "gown": "#f3e5f5"},
]

# ── Patient names for bed labels ─────────────────────────────
PATIENT_NAMES = ["Patient A — Bed 1", "Patient B — Bed 2", "Patient C — Bed 3"]

# ── Helpers ───────────────────────────────────────────────────
def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

def lerp(a, b, t):
    return a + (b - a) * t

def norm_angle(a):
    while a >  math.pi: a -= 2 * math.pi
    while a < -math.pi: a += 2 * math.pi
    return a

def face_yaw(fx, fy, tx, ty):
    return math.atan2(ty - fy, tx - fx)

def place(bid, x, y, z, rx=0, ry=0, rz=0):
    bb.resetBasePose(bid, [x, y, z],
                     bb.getQuaternionFromEuler([rx, ry, rz]))

def clamp(x, y, margin=0.45):
    x = max(-hw + margin, min(hw - margin, x))
    y = max(-hd + margin, min(hd - margin, y))
    return x, y

def box(pos, ext, col):
    return bb.createBody('box', halfExtent=ext, position=pos, color=col, mass=0)

def sph(pos, r, col):
    return bb.createBody('sphere', radius=r, position=pos, color=col, mass=0)


# ═══════════════════════════════════════════════════════════════
#   FLOATING BED LABEL MANAGER
#   Shows live task + vitals text hovering above each bed
# ═══════════════════════════════════════════════════════════════
class BedLabel:
    """Manages 3 lines of floating debug text above a patient bed."""

    # Heights for each text row above the bed
    Z_NAME   = 2.30   # patient name / robot name (top row)
    Z_TASK   = 2.00   # current task description
    Z_VITAL  = 1.72   # latest vital reading
    Z_STATUS = 1.46   # OK / WARN status

    def __init__(self, bed_idx):
        bd = BED[bed_idx]
        self.cx = bd['cx']
        self.cy = bd['cy']
        self.name = PATIENT_NAMES[bed_idx]
        self.robot_name = ROBOT_CFG[bed_idx]['name']
        self._ids = {k: None for k in ('header', 'task', 'vital', 'status')}
        self._draw_all()

    def _quat(self):
        return bb.getQuaternionFromEuler([0, 0, 0])

    def _pos(self, z):
        return (self.cx, self.cy - 0.10, z)

    def _set(self, key, text, z, color, size):
        if self._ids[key] is not None:
            try:
                bb.removeDebugObject(self._ids[key])
            except Exception:
                pass
        self._ids[key] = bb.createDebugText(
            text, self._pos(z), self._quat(), color=color, size=size)

    def _draw_all(self):
        # Header: patient name + robot badge
        self._set('header',
                  f"  ╔═ {self.name}  [{self.robot_name}] ═╗",
                  self.Z_NAME, '#00e5ff', 0.17)
        # Task placeholder
        self._set('task',   "  ⏳ Waiting for robot...",
                  self.Z_TASK, '#b0bec5', 0.15)
        # Vital placeholder
        self._set('vital',  "  📋 No readings yet",
                  self.Z_VITAL, '#b0bec5', 0.14)
        # Status placeholder
        self._set('status', "  ─────────────────────",
                  self.Z_STATUS, '#546e7a', 0.13)

    def set_task(self, msg, color='#fff9c4'):
        self._set('task', f"  🔹 {msg}", self.Z_TASK, color, 0.15)

    def set_vital(self, msg, color='#00e676'):
        self._set('vital', f"  📊 {msg}", self.Z_VITAL, color, 0.14)

    def set_status(self, msg, color='#00e676'):
        self._set('status', f"  {msg}", self.Z_STATUS, color, 0.13)

    def reset(self):
        """Clear task/vital/status back to idle state."""
        self._set('task',   "  ✅ Round complete — resting",
                  self.Z_TASK, '#80cbc4', 0.15)
        self._set('vital',  "  📋 Vitals recorded",
                  self.Z_VITAL, '#80cbc4', 0.14)
        self._set('status', "  ─────────────────────",
                  self.Z_STATUS, '#546e7a', 0.13)


# Global bed label instances (created after ward build)
BED_LABELS = []


# ═══════════════════════════════════════════════════════════════
#   WARD — walls, floor, ceiling features, fixtures
#   NOTE: Top ceiling panel REMOVED for open-top view
# ═══════════════════════════════════════════════════════════════
def build_ward():
    bb.addGroundPlane()

    # ── Floor tiles ──────────────────────────────────────────
    for ix in range(-8, 9):
        for iy in range(-7, 7):
            c = '#ecf0f1' if (ix + iy) % 2 == 0 else '#f8f9fa'
            box([ix + 0.5, iy + 0.5, 0.014], [0.492, 0.492, 0.014], c)

    # Green corridor strip down the centre
    for iy in range(-7, 7):
        box([0.0, iy + 0.5, 0.016], [1.20, 0.490, 0.008], '#e8f5e9')

    # ── Walls ────────────────────────────────────────────────
    # Back wall
    box([0, -hd, WARD_H/2], [hw, 0.09, WARD_H/2], '#ddd8ce')
    # Left wall
    box([-hw, 0, WARD_H/2], [0.09, hd, WARD_H/2], '#e8e3db')
    # Right wall
    box([ hw, 0, WARD_H/2], [0.09, hd, WARD_H/2], '#e8e3db')
    # Front — fully open (no wall, no beam)

    # ── TOP CEILING REMOVED ───────────────────────────────────
    # (ceiling box and its backing strip deleted so the ward is
    #  open-top and floating text labels are clearly visible)

    # ── Light strips (suspended, no ceiling backing) ──────────
    for lx in [-4.5, 0.5, 5.0]:
        box([lx, 0, WARD_H - 0.04], [0.70, 0.20, 0.042], '#fffde7')

    # ── Skirting ─────────────────────────────────────────────
    for pos, ext in [
        ([-hw, 0,   0.06], [0.020, hd, 0.06]),
        ([0, -hd,   0.06], [hw,  0.020, 0.06]),
        ([ hw, 0,   0.06], [0.020, hd, 0.06]),
    ]:
        box(pos, ext, '#b8b0a2')

    # ── Bay divider curtain rails (between beds) ──────────────
    for cx in [-2.2, 2.8]:
        box([cx, 1.2, WARD_H - 0.04], [0.012, 2.80, 0.012], '#90a4ae')
        # Curtain (partially open)
        box([cx, -0.40, WARD_H*0.55], [0.018, 0.80, WARD_H*0.44], '#b0bec5')

    # ── Reception / nurses' station (front-centre) ────────────
    box([0, hd - 0.90, 0.56], [2.20, 0.50, 0.56], '#eceff1')
    box([0, hd - 0.42, 0.56], [2.20, 0.05, 0.56], '#cfd8dc')
    box([0, hd - 0.80, 1.14], [2.20, 0.48, 0.04], '#e0e0e0')
    for mx in [-0.80, 0.80]:
        box([mx, hd - 0.60, 1.22], [0.22, 0.04, 0.18], '#212121')
        box([mx, hd - 0.58, 1.22], [0.18, 0.03, 0.14], '#1b5e20')
    box([0, hd - 0.62, 1.14], [0.14, 0.02, 0.14], '#263238')
    box([0, hd - 0.43, 1.35], [0.55, 0.03, 0.08], '#1565c0')

    # ── Waiting area (front-left corner) ─────────────────────
    for sx in [-6.8, -7.4, -7.8]:
        box([sx, hd - 0.55, 0.22], [0.22, 0.22, 0.22], '#1565c0')
        box([sx, hd - 0.78, 0.46], [0.22, 0.04, 0.26], '#0d47a1')
        box([sx, hd - 0.55, 0.46], [0.24, 0.24, 0.026], '#1976d2')
    box([-7.1, hd - 0.90, 0.44], [0.18, 0.18, 0.44], '#f5f5f5')
    box([-7.1, hd - 0.90, 0.90], [0.20, 0.20, 0.026], '#eeeeee')
    box([-7.8, hd - 1.40, 0.20], [0.12, 0.12, 0.20], '#795548')
    sph([-7.8, hd - 1.40, 0.54], 0.22, '#388e3c')
    sph([-7.8, hd - 1.40, 0.72], 0.14, '#43a047')

    # ── Medicine storage cabinet (back-left wall) ─────────────
    box([-hw + 0.42, -hd + 0.42, 0.90], [0.34, 0.40, 0.90], '#eceff1')
    box([-hw + 0.42, -hd + 0.42, 1.82], [0.36, 0.42, 0.026], '#cfd8dc')
    for dz in [0.30, 0.65, 1.00, 1.38]:
        box([-hw + 0.42, -hd + 0.06, dz], [0.32, 0.016, 0.28], '#f5f5f5')
    for dz, col in [(0.46,'#ef9a9a'),(0.82,'#80cbc4'),(1.16,'#fff9c4'),(1.52,'#ce93d8')]:
        for dx in [-0.16, 0.0, 0.16]:
            box([-hw + 0.42 + dx, -hd + 0.10, dz], [0.040, 0.040, 0.055], col)
            sph([-hw + 0.42 + dx, -hd + 0.10, dz + 0.056], 0.040, col)

    # ── Defibrillator (back-left wall) ───────────────────────
    box([-hw + 0.10, -hd + 1.30, 1.40], [0.08, 0.16, 0.22], '#263238')
    box([-hw + 0.08, -hd + 1.25, 1.40], [0.06, 0.12, 0.18], '#ff5252')
    box([-hw + 0.06, -hd + 1.22, 1.44], [0.04, 0.10, 0.06], '#fffde7')

    # ── Emergency cabinet (back-right wall) ───────────────────
    box([hw - 0.42, -hd + 0.50, 0.80], [0.34, 0.45, 0.80], '#ffebee')
    box([hw - 0.42, -hd + 0.50, 1.62], [0.36, 0.47, 0.026], '#ffcdd2')
    box([hw - 0.42, -hd + 0.07, 0.80], [0.016, 0.016, 0.80], '#e53935')
    for dz in [0.28, 0.58, 0.90, 1.20]:
        box([hw - 0.42, -hd + 0.10, dz], [0.30, 0.016, 0.24], '#ffcdd2')

    # ── Sink station (back wall, centre) ─────────────────────
    box([0, -hd + 0.26, 0.92], [0.28, 0.22, 0.045], '#ffffff')
    box([0, -hd + 0.26, 0.86], [0.26, 0.20, 0.11],  '#eceff1')
    box([0, -hd + 0.26, 0.48], [0.28, 0.22, 0.48],  '#e0e0e0')
    box([0, -hd + 0.26, 1.04], [0.014, 0.014, 0.14], '#90a4ae')
    box([0, -hd + 0.20, 1.16], [0.014, 0.065, 0.014], '#90a4ae')

    # ── Waste bins (each bay) ─────────────────────────────────
    for bx2 in [-4.5, 0.5, 5.0]:
        box([bx2 - 0.85, 2.60, 0.22], [0.14, 0.14, 0.22], '#e0e0e0')
        box([bx2 - 0.85, 2.60, 0.46], [0.15, 0.15, 0.026], '#bdbdbd')

    # ── Notice board (back wall) ──────────────────────────────
    box([-1.20, -hd + 0.10, 1.60], [0.65, 0.07, 0.45], '#8d6e63')
    box([-1.20, -hd + 0.12, 1.60], [0.60, 0.055, 0.40], '#e8f5e9')
    for dz in [0.22, 0.08, -0.08, -0.22]:
        box([-1.20, -hd + 0.14, 1.60 + dz], [0.46, 0.035, 0.010], '#bdbdbd')
    for dx2, col2 in [(-0.30,'#ffcc80'),(-0.10,'#ef9a9a'),(0.10,'#80cbc4'),(0.30,'#fff9c4')]:
        box([-1.20 + dx2, -hd + 0.13, 1.72], [0.065, 0.025, 0.090], col2)

    # ── Clock on back wall ────────────────────────────────────
    sph([2.50, -hd + 0.10, 2.20], 0.18, '#ffffff')
    box([2.50, -hd + 0.06, 2.20], [0.008, 0.005, 0.12], '#333333')
    box([2.50, -hd + 0.06, 2.14], [0.008, 0.090, 0.005], '#333333')
    sph([2.50, -hd + 0.06, 2.20], 0.022, '#e53935')

    # ── Wall monitors (one per bay) ───────────────────────────
    for mx in [-4.5, 0.5, 5.0]:
        box([mx, -hd + 0.09, 1.62], [0.36, 0.08, 0.28], '#263238')
        box([mx, -hd + 0.12, 1.62], [0.30, 0.06, 0.22], '#1b5e20')
        box([mx, -hd + 0.14, 1.70], [0.28, 0.04, 0.007], '#00e676')

    print("[WARD] Hospital ward built ✔  (ceiling removed, open-top)")


# ═══════════════════════════════════════════════════════════════
#   3 PATIENT BEDS
# ═══════════════════════════════════════════════════════════════
def build_all_beds():
    for i, bd in enumerate(BED):
        bx, by = bd['cx'], bd['cy']
        cfg = PAT_CFG[i]

        for lx, ly in [(bx-0.54,by-1.22),(bx+0.54,by-1.22),
                       (bx-0.54,by+1.58),(bx+0.54,by+1.58)]:
            box([lx, ly, 0.12], [0.046, 0.046, 0.24], '#9e9e9e')

        box([bx, by, 0.24], [0.58, 1.22, 0.24], '#e0e0e0')
        box([bx, by, 0.48], [0.55, 1.16, 0.10], '#fafafa')
        box([bx, by+1.08, 0.62], [0.28, 0.28, 0.065], '#ffffff')
        box([bx, by-0.18, 0.54], [0.52, 0.75, 0.06], '#c8e6c9')
        box([bx, by+0.46, 0.54], [0.52, 0.06, 0.065], '#a5d6a7')
        box([bx, by+1.62, 0.72], [0.59, 0.07, 0.46], '#bdbdbd')
        box([bx, by-1.26, 0.52], [0.59, 0.07, 0.30], '#bdbdbd')
        box([bx, by+0.35, 0.70], [0.56, 0.024, 0.090], '#90a4ae')

        box([bx-0.86, by-0.60, 0.40], [0.20, 0.22, 0.40], '#eceff1')
        box([bx-0.86, by-0.60, 0.82], [0.22, 0.24, 0.026], '#cfd8dc')
        sph([bx-0.86, by-0.52, 0.88], 0.030, '#e0f7fa')

        for wx2, wy2 in [(-0.22,0),(0.22,0),(0,-0.22),(0,0.22)]:
            box([bx+0.88+wx2, by+1.20+wy2, 0.026], [0.048, 0.048, 0.026], '#9e9e9e')
        box([bx+0.88, by+1.20, 1.02], [0.026, 0.026, 1.02], '#bdbdbd')
        box([bx+0.88, by+1.20, 2.04], [0.24, 0.026, 0.015], '#bdbdbd')
        box([bx+0.88, by+1.20, 1.86], [0.095, 0.046, 0.17], '#b3e5fc')
        box([bx+0.70, by+1.08, 1.62], [0.020, 0.18, 0.009], '#81d4fa')
        box([bx+0.35, by+0.90, 1.28], [0.009, 0.09, 0.40], '#81d4fa')

        cx2 = CART[i]['x']; cy2 = CART[i]['y']
        box([cx2, cy2, 0.44], [0.26, 0.36, 0.44], '#f5f5f5')
        box([cx2, cy2, 0.90], [0.28, 0.38, 0.026], '#eeeeee')
        for sh in [0.30, 0.60]:
            box([cx2, cy2, sh], [0.24, 0.34, 0.011], '#e0e0e0')
        med_cols = ['#ef9a9a','#80cbc4','#fff9c4','#ce93d8','#ffcc80']
        for mi, (dx2, dy2) in enumerate([(-0.12,-0.20),(0.08,-0.18),
                                          (-0.10,0.12),(0.12,0.08),(0.0,-0.05)]):
            col3 = med_cols[mi % len(med_cols)]
            box([cx2+dx2, cy2+dy2, 0.955], [0.035, 0.035, 0.055], col3)
            sph([cx2+dx2, cy2+dy2, 0.914], 0.035, col3)
        box([cx2-0.10, cy2-0.14, 0.948], [0.072, 0.086, 0.062], '#263238')
        box([cx2-0.10, cy2-0.14, 0.952], [0.058, 0.070, 0.050], '#e53935')
        box([cx2+0.14, cy2+0.04, 0.966], [0.013, 0.013, 0.10], '#e0e0e0')
        sph([cx2+0.14, cy2+0.04, 0.864], 0.020, '#ff8f00')
        box([cx2+0.08, cy2+0.20, 0.950], [0.011, 0.068, 0.011], '#eceff1')
        sph([cx2+0.08, cy2+0.26, 0.950], 0.013, '#90a4ae')
        box([cx2-0.10, cy2+0.18, 0.916], [0.068, 0.082, 0.044], '#80cbc4')
        for wx2, wy2 in [(-0.22,-0.32),(0.22,-0.32),(-0.22,0.32),(0.22,0.32)]:
            sph([cx2+wx2, cy2+wy2, 0.040], 0.040, '#424242')

    print("[BEDS] 3 patient beds + trolleys built ✔")


# ═══════════════════════════════════════════════════════════════
#   3 PATIENTS  (lying in beds)
# ═══════════════════════════════════════════════════════════════
def build_all_patients():
    for i, bd in enumerate(BED):
        bx, by = bd['cx'], bd['cy']
        cfg = PAT_CFG[i]
        sk = cfg['skin']; hr = cfg['hair']; gw = cfg['gown']

        box([bx, by-0.14, 0.62], [0.22, 0.50, 0.14], gw)
        box([bx, by+0.35, 0.62], [0.28, 0.14, 0.10], gw)

        for sx in [-0.30, 0.30]:
            sph([bx+sx, by+0.37, 0.63], 0.088, sk)

        sph([bx, by+1.12, 0.76], 0.188, sk)
        sph([bx, by+1.14, 0.84], 0.186, hr)

        for ex in [bx-0.088, bx+0.088]:
            box([ex, by+0.99, 0.776], [0.040, 0.009, 0.011], '#4a3728')
        sph([bx, by+0.97, 0.742], 0.024, '#f0b27a')
        box([bx, by+0.965, 0.712], [0.046, 0.009, 0.011], '#e59866')
        for ex in [-0.200, 0.200]:
            sph([bx+ex, by+1.10, 0.760], 0.046, sk)

        box([bx-0.32, by+0.46, 0.595], [0.065, 0.32, 0.055], sk)
        sph([bx-0.32, by+0.18, 0.595], 0.074, sk)
        box([bx-0.32, by+0.14, 0.600], [0.022, 0.022, 0.026], '#ff5252')
        box([bx-0.32, by+0.34, 0.595], [0.070, 0.115, 0.062], '#1565c0')

    print("[PATIENTS] 3 patients built ✔")


# ═══════════════════════════════════════════════════════════════
#   SCAN BEAM (one per bay, created per robot)
# ═══════════════════════════════════════════════════════════════
class ScanBeam:
    def __init__(self, bx, by):
        self.bx = bx; self.by = by
        self.beam = bb.createBody('box',
            halfExtent=[0.94, 0.009, 0.005],
            position=[bx, by, 0.007], color='#00e5ff', mass=0)
        self._hide()

    def sweep(self, steps=55):
        ys = self.by - 1.40; ye = self.by + 1.40
        for i in range(steps + 1):
            bb.resetBasePose(self.beam,
                [self.bx, lerp(ys, ye, i/steps), 0.007],
                bb.getQuaternionFromEuler([0, 0, 0]))
            time.sleep(TICK * 1.1)
        self._hide()

    def _hide(self):
        bb.resetBasePose(self.beam,
            [self.bx, self.by, -10],
            bb.getQuaternionFromEuler([0, 0, 0]))


# ═══════════════════════════════════════════════════════════════
#   ROBOT CLASS — parameterised for colour/name
# ═══════════════════════════════════════════════════════════════
class MedRobot:
    def __init__(self, idx):
        self.idx   = idx
        self.cfg   = ROBOT_CFG[idx]
        self.bd    = BED[idx]
        self.dock  = DOCK[idx]
        self.cart  = CART[idx]

        self.x   = self.dock['x']
        self.y   = self.dock['y']
        self.z   = 0.0
        self.yaw = 0.0
        self.arm  = 0.0
        self.larm = 0.0
        self.nod  = 0.0
        self.wt   = 0.0
        self.arm_tgt = (self.dock['x']+1, self.dock['y'], 0.72)
        self.ids = {}
        self.scan = ScanBeam(self.bd['cx'], self.bd['cy'])

        # Reference to this robot's bed label (set after BED_LABELS created)
        self.label = None

        # Legacy HUD refs (kept for print output)
        self._sid = [None]
        self._vid = [None]

    def _mk(self, k, shape, **kw):
        kw['mass'] = 0
        self.ids[k] = bb.createBody(shape, **kw)

    def spawn(self):
        d = [0, 0, -30 - self.idx * 8]
        sc  = self.cfg['scrub']
        acc = self.cfg['accent']
        tl  = self.cfg['tool']

        self._mk('llt','box',  halfExtent=[0.062,0.062,0.178], position=d, color=sc)
        self._mk('lls','box',  halfExtent=[0.052,0.052,0.135], position=d, color=sc)
        self._mk('llf','box',  halfExtent=[0.074,0.046,0.033], position=d, color='white')
        self._mk('rlt','box',  halfExtent=[0.062,0.062,0.178], position=d, color=sc)
        self._mk('rls','box',  halfExtent=[0.052,0.052,0.135], position=d, color=sc)
        self._mk('rlf','box',  halfExtent=[0.074,0.046,0.033], position=d, color='white')
        self._mk('pants','box', halfExtent=[0.155,0.102,0.165], position=d, color=sc)
        self._mk('belt', 'box', halfExtent=[0.158,0.105,0.022], position=d, color=acc)
        self._mk('torso','box', halfExtent=[0.165,0.112,0.272], position=d, color='#ffffff')
        self._mk('apron','box', halfExtent=[0.104,0.023,0.232], position=d, color='#f1f8e9')
        self._mk('crsH', 'box', halfExtent=[0.047,0.009,0.013], position=d, color='#e53935')
        self._mk('crsV', 'box', halfExtent=[0.013,0.009,0.047], position=d, color='#e53935')
        self._mk('tag',  'box', halfExtent=[0.042,0.009,0.022], position=d, color=acc)
        self._mk('sttU','box',  halfExtent=[0.008,0.008,0.105], position=d, color='#37474f')
        self._mk('sttD','sphere',radius=0.026,                  position=d, color='#546e7a')
        self._mk('neck','box',  halfExtent=[0.054,0.054,0.070], position=d, color='#f5cba7')
        self._mk('head','sphere',radius=0.162,                  position=d, color='#f5cba7')
        self._mk('hair','sphere',radius=0.160,                  position=d, color='#4e342e')
        self._mk('hrbk','sphere',radius=0.055,                  position=d, color='#4e342e')
        self._mk('ewl', 'sphere',radius=0.054,                  position=d, color='white')
        self._mk('ewr', 'sphere',radius=0.054,                  position=d, color='white')
        self._mk('epl', 'sphere',radius=0.036,                  position=d, color='#1a237e')
        self._mk('epr', 'sphere',radius=0.036,                  position=d, color='#1a237e')
        self._mk('ebl', 'box',   halfExtent=[0.042,0.007,0.009],position=d, color='#4e342e')
        self._mk('ebr', 'box',   halfExtent=[0.042,0.007,0.009],position=d, color='#4e342e')
        self._mk('nose','sphere',radius=0.023,                  position=d, color='#f0b27a')
        self._mk('mth', 'box',   halfExtent=[0.052,0.008,0.011],position=d, color='#e57373')
        self._mk('earl','sphere',radius=0.038,                  position=d, color='#f5cba7')
        self._mk('earr','sphere',radius=0.038,                  position=d, color='#f5cba7')
        self._mk('cap', 'box',   halfExtent=[0.152,0.114,0.042],position=d, color='white')
        self._mk('cap2','box',   halfExtent=[0.108,0.080,0.060],position=d, color='white')
        self._mk('cpst','box',   halfExtent=[0.155,0.116,0.012],position=d, color=acc)
        self._mk('cpcH','box',   halfExtent=[0.033,0.007,0.010],position=d, color='#e53935')
        self._mk('cpcV','box',   halfExtent=[0.010,0.007,0.033],position=d, color='#e53935')
        self._mk('lau', 'box',   halfExtent=[0.052,0.052,0.162],position=d, color='#ffffff')
        self._mk('lal', 'box',   halfExtent=[0.044,0.044,0.130],position=d, color='#f5cba7')
        self._mk('lah', 'sphere',radius=0.054,                  position=d, color='#f5cba7')
        self._mk('clip','box',   halfExtent=[0.080,0.016,0.108],position=d, color='#8d6e63')
        self._mk('papr','box',   halfExtent=[0.070,0.012,0.095],position=d, color='white')
        self._mk('ln1', 'box',   halfExtent=[0.054,0.006,0.008],position=d, color='#bdbdbd')
        self._mk('ln2', 'box',   halfExtent=[0.054,0.006,0.008],position=d, color='#bdbdbd')
        self._mk('ln3', 'box',   halfExtent=[0.044,0.006,0.008],position=d, color=acc)
        self._mk('rau', 'box',   halfExtent=[0.052,0.052,0.162],position=d, color='#ffffff')
        self._mk('ral', 'box',   halfExtent=[0.044,0.044,0.130],position=d, color='#f5cba7')
        self._mk('rah', 'sphere',radius=0.054,                  position=d, color='#f5cba7')
        self._mk('tool','box',   halfExtent=[0.026,0.026,0.088],position=d, color='#37474f')
        self._mk('tolL','sphere',radius=0.034,                  position=d, color=tl)

        self.update()
        print(f"[ROBOT-{self.idx+1}] {self.cfg['name']} spawned ✔")

    # ── Spatial transform helpers ──────────────────────────────
    def _w(self, lx, ly, lz):
        cy = math.cos(self.yaw); sy = math.sin(self.yaw)
        return (self.x + cy*lx - sy*ly,
                self.y + sy*lx + cy*ly,
                self.z + lz)

    def _p(self, key, lx, ly, lz, rx=0, ry=0):
        wx, wy, wz = self._w(lx, ly, lz)
        place(self.ids[key], wx, wy, wz, rx, ry, self.yaw)

    def update(self):
        a=self.arm; la=self.larm; nd=self.nod; wt=self.wt
        LL = math.sin(wt)*0.068; RL = math.sin(wt+math.pi)*0.068

        self._p('llt',-0.108, LL*0.5, 0.296)
        self._p('lls',-0.108, LL*0.25,0.098)
        self._p('llf',-0.108, 0,      0.024)
        self._p('rlt', 0.108, RL*0.5, 0.296)
        self._p('rls', 0.108, RL*0.25,0.098)
        self._p('rlf', 0.108, 0,      0.024)
        self._p('pants',0,0,  0.422)
        self._p('belt', 0,0,  0.590)
        self._p('torso',0,0,  0.778)
        self._p('apron',0,-0.116, 0.772)
        self._p('crsH', 0,-0.126, 0.886)
        self._p('crsV', 0,-0.126, 0.886)
        self._p('tag',  0,-0.126, 0.844)
        self._p('sttU', 0,-0.066, 0.920)
        self._p('sttD', 0,-0.074, 0.814)
        self._p('neck', 0,0,  1.068)

        hx,hy,hz = self._w(0,0,1.262)
        place(self.ids['head'],hx,hy,hz,      nd,0,self.yaw)
        place(self.ids['hair'],hx,hy,hz+0.062,nd,0,self.yaw)
        place(self.ids['hrbk'],hx,hy+0.098,hz+0.060,nd,0,self.yaw)

        cx,ccy,cz = self._w(0,0,1.460)
        place(self.ids['cap'], cx,ccy,cz,       nd,0,self.yaw)
        place(self.ids['cap2'],cx,ccy,cz+0.058, nd,0,self.yaw)
        place(self.ids['cpst'],cx,ccy,cz-0.022, nd,0,self.yaw)
        place(self.ids['cpcH'],cx,ccy,cz+0.050, nd,0,self.yaw)
        place(self.ids['cpcV'],cx,ccy,cz+0.050, nd,0,self.yaw)

        self._p('ewl',-0.068,-0.132,1.282,nd)
        self._p('ewr', 0.068,-0.132,1.282,nd)
        self._p('epl',-0.068,-0.146,1.282,nd)
        self._p('epr', 0.068,-0.146,1.282,nd)
        self._p('ebl',-0.068,-0.146,1.310,nd)
        self._p('ebr', 0.068,-0.146,1.310,nd)
        self._p('nose',0,    -0.156,1.248,nd)
        self._p('mth', 0,    -0.154,1.216,nd)
        self._p('earl',-0.206,0.012,1.262,nd)
        self._p('earr', 0.206,0.012,1.262,nd)

        wzh = 0.355 + la*0.295; lly = -la*0.158
        self._p('lau',-0.240,0,     0.852+la*0.128)
        self._p('lal',-0.240,lly,   0.548+la*0.215)
        self._p('lah',-0.240,lly,   wzh)
        clx,cly,clz = self._w(-0.240, lly-0.018, wzh+0.006)
        place(self.ids['clip'],clx,cly,clz,0,0,self.yaw)
        place(self.ids['papr'],clx,cly,clz,0,0,self.yaw)
        place(self.ids['ln1'], clx,cly,clz+0.046,0,0,self.yaw)
        place(self.ids['ln2'], clx,cly,clz+0.013,0,0,self.yaw)
        place(self.ids['ln3'], clx,cly,clz-0.022,0,0,self.yaw)

        tx,ty,tz = self.arm_tgt
        cr=math.cos(self.yaw); sr=math.sin(self.yaw)
        lx1= cr*(tx-self.x)+sr*(ty-self.y)
        ly1=-sr*(tx-self.x)+cr*(ty-self.y)
        lz1=tz-self.z; t_=ease(a)
        hlx=lerp(0.240,lx1,t_); hly=lerp(0,ly1,t_); hlz=lerp(0.330,lz1,t_)
        self._p('rau',0.240,lerp(0,ly1*0.28,t_),lerp(0.852,lz1*0.72,t_),-t_*0.85)
        self._p('ral',lerp(0.240,hlx*0.82,t_),lerp(0,hly*0.62,t_),lerp(0.548,hlz*0.78,t_))
        hwx,hwy,hwz = self._w(hlx,hly,hlz)
        place(self.ids['rah'], hwx,hwy,hwz,0,0,self.yaw)
        place(self.ids['tool'],hwx,hwy,hwz,0,0,self.yaw)
        place(self.ids['tolL'],hwx,hwy,hwz+0.094,0,0,self.yaw)

    def set_target(self,tx,ty,tz): self.arm_tgt=(tx,ty,tz)
    def set_pose(self,x,y,yaw):
        x,y=clamp(x,y)
        self.x,self.y,self.yaw=x,y,yaw; self.update()

    # ── Status helpers — now drive BOTH print + bed label ────
    def status(self, msg, col='#a5d6a7'):
        # Legacy print
        print(f"   [{self.cfg['name']}] {msg}")
        # Floating label above bed
        if self.label:
            self.label.set_task(msg, col)

    def show_vitals(self, line):
        print(f"   [{self.cfg['name']}] Vitals: {line}")
        if self.label:
            self.label.set_vital(line)

    def show_status_ok(self, line):
        """Green OK/NORMAL result."""
        if self.label:
            self.label.set_status(f"✅ {line}", '#00e676')

    def show_status_warn(self, line):
        """Red/orange warning result."""
        if self.label:
            self.label.set_status(f"⚠️  {line}", '#ff5252')


# ═══════════════════════════════════════════════════════════════
#   MOTION HELPERS
# ═══════════════════════════════════════════════════════════════
def walk_to(r, tx, ty, spd=1.80):
    tx, ty = clamp(tx, ty)
    sx, sy = r.x, r.y
    dx, dy = tx-sx, ty-sy
    d = math.sqrt(dx*dx+dy*dy)
    if d < 0.030: return
    turn_to(r, math.atan2(dy,dx), steps=20)
    steps = max(1, int(d/(spd*TICK)))
    for i in range(steps+1):
        t = ease(i/steps)
        r.x, r.y = clamp(lerp(sx,tx,t), lerp(sy,ty,t))
        r.wt += 0.20; r.update(); time.sleep(TICK)
    r.x, r.y = clamp(tx, ty); r.wt=0.0; r.update()

def turn_to(r, tyaw, steps=22):
    start=r.yaw; diff=norm_angle(tyaw-start)
    if abs(diff)<0.010: return
    for i in range(steps+1):
        r.yaw=start+diff*ease(i/steps); r.update(); time.sleep(TICK)

def move_arm(r, tgt, steps=38):
    start=r.arm
    for i in range(steps+1):
        r.arm=lerp(start,tgt,ease(i/steps)); r.update(); time.sleep(TICK)

def move_larm(r, tgt, steps=28):
    start=r.larm
    for i in range(steps+1):
        r.larm=lerp(start,tgt,ease(i/steps)); r.update(); time.sleep(TICK)

def do_nod(r, amp=0.28, reps=2):
    for _ in range(reps):
        for i in range(20):
            r.nod=amp*math.sin(math.pi*i/19); r.update(); time.sleep(TICK)
    r.nod=0.0; r.update()

def do_wave(r, reps=3):
    for _ in range(reps):
        move_arm(r,0.74,steps=12); time.sleep(0.05)
        move_arm(r,0.46,steps=10); time.sleep(0.04)
    move_arm(r,0.0,steps=16)

def do_spin(r, steps=50):
    start=r.yaw
    for i in range(steps+1):
        r.yaw=start+2*math.pi*ease(i/steps); r.update(); time.sleep(TICK)
    r.yaw=start; r.update()

def pulse(r, count=3):
    for _ in range(count):
        r.nod=0.10; r.update(); time.sleep(0.22)
        r.nod=0.0;  r.update(); time.sleep(0.22)


# ═══════════════════════════════════════════════════════════════
#   INDIVIDUAL ROBOT SEQUENCES
# ═══════════════════════════════════════════════════════════════

# ── ARIA (Robot 0): BP + Blood + Temp + O2 ──────────────────
def sequence_aria(r):
    bd = r.bd; cx=bd['cx']; cy=bd['cy']
    bx=cx; by=cy
    p_head_y=by+1.12; p_head_z=0.76
    p_arm_x=cx-0.32; p_arm_y=by+0.20; p_arm_z=0.60

    bp_s=random.randint(105,155); bp_d=random.randint(65,100)
    blood=round(random.uniform(11.0,16.8),1)
    temp=round(random.uniform(35.6,39.4),1)
    o2=random.randint(88,100)

    r.status("Walking to scan zone 🚶", '#80deea')
    walk_to(r, cx-1.10, cy-0.25)
    turn_to(r, face_yaw(r.x,r.y,cx,cy), steps=20)

    r.status("Scanning patient 🔍", '#80deea')
    move_larm(r, 0.50, steps=14)
    r.scan.sweep(steps=55)
    do_nod(r, amp=0.14, reps=1); time.sleep(0.20)

    r.status("Collecting instruments 🧰", '#ffe082')
    walk_to(r, r.cart['x']-0.32, r.cart['y'])
    turn_to(r, face_yaw(r.x,r.y,r.cart['x'],r.cart['y']), steps=18)
    r.set_target(r.cart['x']-0.08, r.cart['y']-0.10, 0.96)
    move_arm(r, 0.90, steps=28); time.sleep(0.26)
    move_arm(r, 0.0,  steps=20); time.sleep(0.16)

    r.status("Good morning! Checking your vitals 👋", '#fff9c4')
    walk_to(r, cx-0.82, cy+0.60)
    turn_to(r, face_yaw(r.x,r.y,cx,p_head_y), steps=22)
    do_nod(r, amp=0.22, reps=2); time.sleep(0.20)

    # BP
    r.status("Blood Pressure check 💉", '#ef9a9a')
    r.set_target(p_arm_x, p_arm_y+0.18, p_arm_z)
    move_arm(r, 1.0, steps=40); time.sleep(0.32)
    pulse(r, count=4)
    ok = 90<=bp_s<=130
    r.show_vitals(f"BP: {bp_s}/{bp_d} {'✔' if ok else '⚠'}")
    if ok: r.show_status_ok(f"BP {bp_s}/{bp_d} — NORMAL")
    else:  r.show_status_warn(f"BP {bp_s}/{bp_d} — HIGH")
    r.status(f"BP={bp_s}/{bp_d} — {'NORMAL ✔' if ok else 'HIGH ⚠'}", '#00e676' if ok else '#ff5252')
    move_larm(r,0.80,steps=12); time.sleep(0.22); move_larm(r,0.54,steps=10)
    move_arm(r,0.0,steps=24); time.sleep(0.22)

    # Blood
    r.status("Blood level check 🩸", '#ef9a9a')
    r.set_target(p_arm_x, p_arm_y, p_arm_z)
    move_arm(r, 1.0, steps=38); time.sleep(0.32)
    pulse(r, count=3)
    bl_ok = 12.0<=blood<=16.0
    r.show_vitals(f"Blood:{blood}g/dL {'✔' if bl_ok else '⚠'}")
    if bl_ok: r.show_status_ok(f"Blood {blood}g/dL — NORMAL")
    else:     r.show_status_warn(f"Blood {blood}g/dL — LOW")
    r.status(f"Blood={blood}g/dL — {'NORMAL ✔' if bl_ok else 'LOW ⚠'}", '#00e676' if bl_ok else '#ff9800')
    move_larm(r,0.84,steps=12); time.sleep(0.22); move_larm(r,0.58,steps=10)
    move_arm(r,0.0,steps=24); time.sleep(0.22)

    # Temp
    r.status("Temperature check 🌡️", '#ffcc80')
    r.set_target(bx, p_head_y-0.05, p_head_z)
    move_arm(r, 1.0, steps=38); time.sleep(0.32)
    pulse(r, count=2)
    t_ok = 36.0<=temp<=37.5
    r.show_vitals(f"Temp:{temp}°C {'✔' if t_ok else '⚠'}")
    if t_ok: r.show_status_ok(f"Temp {temp}°C — NORMAL")
    else:    r.show_status_warn(f"Temp {temp}°C — FEVER")
    r.status(f"Temp={temp}°C — {'NORMAL ✔' if t_ok else 'FEVER ⚠'}", '#00e676' if t_ok else '#ff5252')
    move_larm(r,0.88,steps=12); time.sleep(0.24); move_larm(r,0.62,steps=10)
    move_arm(r,0.0,steps=24); time.sleep(0.22)

    # O2
    r.status("O2 Saturation check 💊", '#b3e5fc')
    r.set_target(p_arm_x, p_arm_y-0.04, p_arm_z)
    move_arm(r, 1.0, steps=36); time.sleep(0.32)
    pulse(r, count=2)
    o2_ok = o2>=95
    r.show_vitals(f"O2:{o2}% {'✔' if o2_ok else '⚠'}")
    if o2_ok: r.show_status_ok(f"O2 {o2}% — NORMAL")
    else:     r.show_status_warn(f"O2 {o2}% — LOW")
    r.status(f"O2={o2}% — {'NORMAL ✔' if o2_ok else 'LOW ⚠'}", '#00e676' if o2_ok else '#ff5252')
    move_larm(r,0.82,steps=12); time.sleep(0.22); move_larm(r,0.56,steps=10)
    move_arm(r,0.0,steps=24); time.sleep(0.22)

    r.status("Recording vitals 📋", '#b2dfdb')
    move_larm(r,1.0,steps=16); do_nod(r,amp=0.12,reps=3); time.sleep(0.28)
    move_larm(r,0.60,steps=12); time.sleep(0.18)

    r.status("IV drip check 💧", '#b3e5fc')
    walk_to(r, bx+0.20, by-1.42)
    turn_to(r, face_yaw(r.x,r.y,bx+0.88,by+1.20), steps=16)
    r.set_target(bx+0.72, by+1.10, 1.62)
    move_arm(r,0.80,steps=24); time.sleep(0.24); pulse(r,count=2)
    move_arm(r,0.0,steps=18)
    r.status("IV flow NORMAL ✔", '#00e676'); time.sleep(0.18)

    r.status("Rest well! Goodbye 👋", '#fff9c4')
    walk_to(r, cx-0.82, cy+0.60)
    turn_to(r, face_yaw(r.x,r.y,cx,p_head_y), steps=20)
    do_nod(r,amp=0.26,reps=1); do_wave(r,reps=3); time.sleep(0.16)

    r.status("Check complete! 🎉", '#80cbc4')
    do_spin(r, steps=48); move_larm(r,0.0,steps=12); time.sleep(0.22)

    r.status("Returning to dock 🚶", '#b0bec5')
    walk_to(r, r.dock['x'], r.dock['y'])
    turn_to(r, 0.0, steps=14)
    r.status("Standby at dock ✔", '#80deea')
    if r.label: r.label.reset()


# ── NOVA (Robot 1): BP + ECG + Glucose ──────────────────────
def sequence_nova(r):
    bd=r.bd; cx=bd['cx']; cy=bd['cy']
    bx=cx; by=cy
    p_head_y=by+1.12; p_head_z=0.76
    p_arm_x=cx-0.32; p_arm_y=by+0.20; p_arm_z=0.60

    bp_s=random.randint(108,148); bp_d=random.randint(68,96)
    glucose=round(random.uniform(3.5,11.0),1)
    ecg_hr=random.randint(55,120)

    r.status("Walking to scan zone 🚶", '#80deea')
    walk_to(r, cx-1.10, cy-0.25)
    turn_to(r, face_yaw(r.x,r.y,cx,cy), steps=20)

    r.status("Full body scan 🔍", '#80deea')
    move_larm(r,0.50,steps=14)
    r.scan.sweep(steps=55)
    do_nod(r,amp=0.14,reps=1); time.sleep(0.20)

    r.status("Picking up ECG leads + kit 🧰", '#ffe082')
    walk_to(r, r.cart['x']-0.32, r.cart['y'])
    turn_to(r, face_yaw(r.x,r.y,r.cart['x'],r.cart['y']), steps=18)
    r.set_target(r.cart['x'], r.cart['y'], 0.96)
    move_arm(r,0.88,steps=28); time.sleep(0.24); move_arm(r,0.0,steps=18)

    r.status("Hello! ECG + glucose today 👋", '#fff9c4')
    walk_to(r, cx-0.82, cy+0.60)
    turn_to(r, face_yaw(r.x,r.y,cx,p_head_y), steps=22)
    do_nod(r,amp=0.20,reps=2); time.sleep(0.18)

    # BP
    r.status("Blood Pressure 💉", '#ef9a9a')
    r.set_target(p_arm_x, p_arm_y+0.18, p_arm_z)
    move_arm(r,1.0,steps=40); time.sleep(0.30)
    pulse(r,count=4)
    ok=90<=bp_s<=130
    r.show_vitals(f"BP:{bp_s}/{bp_d} {'✔' if ok else '⚠'}")
    if ok: r.show_status_ok(f"BP {bp_s}/{bp_d} — OK")
    else:  r.show_status_warn(f"BP {bp_s}/{bp_d} — HIGH")
    r.status(f"BP={bp_s}/{bp_d} — {'OK ✔' if ok else 'HIGH ⚠'}", '#00e676' if ok else '#ff5252')
    move_larm(r,0.80,steps=12); time.sleep(0.20); move_larm(r,0.54,steps=10)
    move_arm(r,0.0,steps=24); time.sleep(0.20)

    # ECG
    r.status("ECG — attaching chest leads ❤️", '#ef9a9a')
    r.set_target(bx, by+0.60, 0.68)
    move_arm(r,1.0,steps=40); time.sleep(0.28)
    pulse(r,count=5)
    ecg_ok = 60<=ecg_hr<=100
    r.show_vitals(f"HR:{ecg_hr}bpm {'✔' if ecg_ok else '⚠'}")
    if ecg_ok: r.show_status_ok(f"ECG HR={ecg_hr}bpm — NORMAL")
    else:      r.show_status_warn(f"ECG HR={ecg_hr}bpm — IRREGULAR")
    r.status(f"ECG HR={ecg_hr}bpm — {'NORMAL ✔' if ecg_ok else 'IRREGULAR ⚠'}", '#00e676' if ecg_ok else '#ff5252')
    move_larm(r,0.86,steps=12); time.sleep(0.22); move_larm(r,0.60,steps=10)
    move_arm(r,0.0,steps=24); time.sleep(0.20)

    # Glucose
    r.status("Blood Glucose check 🍬", '#ffcc80')
    r.set_target(p_arm_x, p_arm_y, p_arm_z)
    move_arm(r,1.0,steps=38); time.sleep(0.30)
    pulse(r,count=3)
    gl_ok = 3.9<=glucose<=7.8
    r.show_vitals(f"Gluc:{glucose}mmol {'✔' if gl_ok else '⚠'}")
    if gl_ok: r.show_status_ok(f"Glucose {glucose}mmol/L — NORMAL")
    else:     r.show_status_warn(f"Glucose {glucose}mmol/L — HIGH")
    r.status(f"Glucose={glucose}mmol/L — {'NORMAL ✔' if gl_ok else 'HIGH ⚠'}", '#00e676' if gl_ok else '#ff5252')
    move_larm(r,0.84,steps=12); time.sleep(0.22); move_larm(r,0.58,steps=10)
    move_arm(r,0.0,steps=24); time.sleep(0.20)

    r.status("Recording on chart 📋", '#b2dfdb')
    move_larm(r,1.0,steps=16); do_nod(r,amp=0.12,reps=3); time.sleep(0.26)
    move_larm(r,0.60,steps=12); time.sleep(0.16)

    r.status("Feel better soon! 👋", '#fff9c4')
    walk_to(r, cx-0.82, cy+0.60)
    turn_to(r, face_yaw(r.x,r.y,cx,p_head_y), steps=20)
    do_nod(r,amp=0.24,reps=1); do_wave(r,reps=3)

    r.status("NOVA — check complete! 🎉", '#80cbc4')
    do_spin(r,steps=48); move_larm(r,0.0,steps=12); time.sleep(0.20)

    r.status("Returning to dock 🚶", '#b0bec5')
    walk_to(r, r.dock['x'], r.dock['y'])
    turn_to(r, 0.0, steps=14)
    r.status("Standby ✔", '#80deea')
    if r.label: r.label.reset()


# ── ZETA (Robot 2): Temp + O2 + Neuro reflex ─────────────────
def sequence_zeta(r):
    bd=r.bd; cx=bd['cx']; cy=bd['cy']
    bx=cx; by=cy
    p_head_y=by+1.12; p_head_z=0.76
    p_arm_x=cx-0.32; p_arm_y=by+0.20; p_arm_z=0.60

    temp=round(random.uniform(35.8,39.2),1)
    o2=random.randint(90,100)
    reflex=random.choice(['Normal','Sluggish','Brisk'])

    r.status("Walking to scan zone 🚶", '#80deea')
    walk_to(r, cx-1.10, cy-0.25)
    turn_to(r, face_yaw(r.x,r.y,cx,cy), steps=20)

    r.status("Neuro-scan initiated 🔍", '#80deea')
    move_larm(r,0.50,steps=14)
    r.scan.sweep(steps=55)
    do_nod(r,amp=0.14,reps=1); time.sleep(0.20)

    r.status("Gathering neuro + temp kit 🧰", '#ffe082')
    walk_to(r, r.cart['x']-0.32, r.cart['y'])
    turn_to(r, face_yaw(r.x,r.y,r.cart['x'],r.cart['y']), steps=18)
    r.set_target(r.cart['x']+0.08, r.cart['y']+0.10, 0.96)
    move_arm(r,0.90,steps=28); time.sleep(0.24); move_arm(r,0.0,steps=18)

    r.status("Good morning! Neuro round today 👋", '#fff9c4')
    walk_to(r, cx-0.82, cy+0.60)
    turn_to(r, face_yaw(r.x,r.y,cx,p_head_y), steps=22)
    do_nod(r,amp=0.22,reps=2); time.sleep(0.18)

    # Temp
    r.status("Temperature — forehead scan 🌡️", '#ffcc80')
    r.set_target(bx, p_head_y-0.04, p_head_z)
    move_arm(r,1.0,steps=38); time.sleep(0.30)
    pulse(r,count=2)
    t_ok=36.0<=temp<=37.5
    r.show_vitals(f"Temp:{temp}°C {'✔' if t_ok else 'FEVER⚠'}")
    if t_ok: r.show_status_ok(f"Temp {temp}°C — NORMAL")
    else:    r.show_status_warn(f"Temp {temp}°C — FEVER")
    r.status(f"Temp={temp}°C — {'NORMAL ✔' if t_ok else 'FEVER ⚠'}", '#00e676' if t_ok else '#ff5252')
    move_larm(r,0.86,steps=12); time.sleep(0.22); move_larm(r,0.60,steps=10)
    move_arm(r,0.0,steps=24); time.sleep(0.20)

    # O2
    r.status("O2 Saturation — pulse ox 💊", '#b3e5fc')
    r.set_target(p_arm_x, p_arm_y-0.04, p_arm_z)
    move_arm(r,1.0,steps=36); time.sleep(0.30)
    pulse(r,count=2)
    o2_ok=o2>=95
    r.show_vitals(f"O2:{o2}% {'✔' if o2_ok else '⚠'}")
    if o2_ok: r.show_status_ok(f"O2 {o2}% — NORMAL")
    else:     r.show_status_warn(f"O2 {o2}% — LOW")
    r.status(f"O2={o2}% — {'NORMAL ✔' if o2_ok else 'LOW ⚠'}", '#00e676' if o2_ok else '#ff5252')
    move_larm(r,0.82,steps=12); time.sleep(0.22); move_larm(r,0.56,steps=10)
    move_arm(r,0.0,steps=24); time.sleep(0.20)

    # Neuro
    r.status("Neurological reflex test 🧠", '#ce93d8')
    r.set_target(bx, by-0.10, 0.68)
    move_arm(r,0.90,steps=38); time.sleep(0.28)
    pulse(r,count=4)
    r.show_vitals(f"Reflex:{reflex}")
    if reflex=='Normal': r.show_status_ok(f"Reflex = {reflex}")
    else:                r.show_status_warn(f"Reflex = {reflex}")
    r.status(f"Reflex = {reflex} {'✔' if reflex=='Normal' else '⚠'}", '#00e676' if reflex=='Normal' else '#ff9800')
    move_larm(r,0.88,steps=12); time.sleep(0.24); move_larm(r,0.62,steps=10)
    move_arm(r,0.0,steps=24); time.sleep(0.20)

    r.status("Recording neuro chart 📋", '#b2dfdb')
    move_larm(r,1.0,steps=16); do_nod(r,amp=0.12,reps=3); time.sleep(0.26)
    move_larm(r,0.60,steps=12); time.sleep(0.16)

    r.status("Great progress! Rest up 👋", '#fff9c4')
    walk_to(r, cx-0.82, cy+0.60)
    turn_to(r, face_yaw(r.x,r.y,cx,p_head_y), steps=20)
    do_nod(r,amp=0.26,reps=1); do_wave(r,reps=3)

    r.status("ZETA — check complete! 🎉", '#80cbc4')
    do_spin(r,steps=48); move_larm(r,0.0,steps=12); time.sleep(0.20)

    r.status("Returning to dock 🚶", '#b0bec5')
    walk_to(r, r.dock['x'], r.dock['y'])
    turn_to(r,0.0,steps=14)
    r.status("Standby ✔", '#80deea')
    if r.label: r.label.reset()


# ═══════════════════════════════════════════════════════════════
#   SEQUENTIAL RUNNER
# ═══════════════════════════════════════════════════════════════
SEQUENCES = [sequence_aria, sequence_nova, sequence_zeta]

def run_robot(r, seq_fn):
    try:
        r.arm=0.0; r.larm=0.0; r.nod=0.0; r.wt=0.0
        r.set_target(r.dock['x']+1, r.dock['y'], 0.72)
        r.set_pose(r.dock['x'], r.dock['y'], 0.0)
        seq_fn(r)
    except Exception as e:
        print(f"[ERROR] {r.cfg['name']}: {e}")


# ═══════════════════════════════════════════════════════════════
#   MAIN
# ═══════════════════════════════════════════════════════════════
print("=" * 60)
print("  CITY HOSPITAL — WARD A")
print("  3 Medical Robots × 3 Patients")
print("  ARIA: BP+Blood+Temp+O2  |  NOVA: BP+ECG+Glucose")
print("  ZETA: Temp+O2+Neuro")
print("  UPGRADES: Ceiling removed | Floating bed-side labels")
print("=" * 60)

build_ward()
build_all_beds()
build_all_patients()

# ── Create bed label overlays (after ward geometry exists) ────
for i in range(3):
    BED_LABELS.append(BedLabel(i))
print("[LABELS] Floating bed labels created ✔")

# ── Spawn robots and link labels ──────────────────────────────
robots = [MedRobot(i) for i in range(3)]
for r in robots:
    r.spawn()
    r.label = BED_LABELS[r.idx]   # ← link robot to its bed label
    time.sleep(0.4)

# ── Ward title bar (floor-level, always visible) ──────────────
bb.createDebugText(
    "  CITY HOSPITAL — WARD A  |  3 Robots  |  3 Patients",
    (0, -hd - 0.30, 0.14),
    bb.getQuaternionFromEuler([0,0,0]),
    color='#00e5ff', size=0.22)

print("\nAll systems ready — starting health rounds in 3s...")
time.sleep(3.0)

run_no = 0
while True:
    run_no += 1
    print(f"\n{'='*55}")
    print(f"  HEALTH ROUND #{run_no}")
    print(f"{'='*55}")

    # Update round counter on each bed label header
    for lbl in BED_LABELS:
        lbl.set_task(f"Round #{run_no} starting...", '#80deea')

    for r, seq_fn in zip(robots, SEQUENCES):
        print(f"\n  [{r.cfg['name']}] Starting health check...")
        run_robot(r, seq_fn)
        print(f"  [{r.cfg['name']}] Done. Next robot in 2s...")
        time.sleep(2.0)

    print(f"\n  Round #{run_no} complete. Next round in 6s...")
    time.sleep(6.0)
