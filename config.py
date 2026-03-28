# config.py – all constants, no logic
W, H    = 1920, 1080
FPS     = 60
TITLE   = "Tiberium Strike Force  ·  ECS Edition"

TILE    = 32          # px per map tile
MAP_W   = 120         # tiles wide
MAP_H   = 120         # tiles tall

PLAYER, ENEMY = 0, 1

# terrain IDs
TGRASS, TDIRT, TROCK, TWATER = 0, 1, 2, 3

HUD_H = 112
MINI  = 240   # minimap px size

ZOOM_MIN  = 0.5
ZOOM_MAX  = 2.0
ZOOM_STEP = 0.1

# ── Colour palette ────────────────────────────────────────────────────────────
P = {
    'bg':      (  4,   8,   4),
    'player':  ( 30, 180, 255),
    'enemy':   (255,  60,  30),
    'neutral': (150, 160, 150),
    'select':  (  0, 255, 130),
    'tib':     ( 20, 190,  40),
    'tib_hi':  ( 60, 255,  90),
    'hp_hi':   (  0, 230,  60),
    'hp_mid':  (255, 200,   0),
    'hp_lo':   (255,  40,   0),
    'ui_bg':   (  6,  12,   6),
    'ui_brd':  (  0, 160,  40),
    'ui_hi':   (  0, 220,  60),
    'gold':    (255, 210,   0),
    'white':   (230, 240, 230),
    'gray':    (100, 110, 100),
    'fire_hi': (255, 240,  40),
    'fire_lo': (255, 120,   0),
    'smoke':   ( 80,  85,  80),
    'proj_p':  ( 80, 200, 255),
    'proj_e':  (255,  80,  40),
    'shell':   (255, 220,  80),
    'bang':    (255, 160,   0),
    'build_ok':(  0, 220,  80),
    'build_no':(220,  40,  40),
    # ── crazy attack FX colours ──
    'elec':    (120, 200, 255),    # electric blue
    'elec_hi': (200, 240, 255),    # bright electric white-blue
    'plasma':  (200,  60, 255),    # purple plasma
    'nova':    (255, 255, 200),    # bright nova flash
    'laser_p': (  0, 180, 255),    # player laser tint
    'laser_e': (255, 100,  30),    # enemy laser tint
    # ── new tank FX colours ──
    'rocket':  (255, 140,  40),    # rocket exhaust orange
    'rocket_hi':(255, 220, 100),   # rocket bright trail
    'tesla':   (100, 160, 255),    # tesla arc core
    'tesla_hi':(200, 230, 255),    # tesla bright flash
    'tesla_bg':(  60, 100, 200),   # tesla background glow
    'laser_r': (255,  20,  20),    # red laser
    'laser_g': ( 20, 255,  80),    # green laser
    'flame':   (255, 100,  10),    # flame base
    'flame_hi':(255, 220,  60),    # flame bright
    'flame_wh':(255, 255, 200),    # flame white-hot core
}



# terrain base-colours per type (3 shades for variation)
TCOLORS = {
    TGRASS: [(24, 56, 16), (28, 60, 20), (20, 50, 14)],
    TDIRT:  [(72, 58, 36), (80, 62, 38), (62, 52, 32)],
    TROCK:  [(60, 60, 56), (68, 66, 60), (52, 52, 48)],
    TWATER: [(14, 32, 68), (16, 36, 74), (10, 26, 58)],
}

# ── Unit data: hp, speed, dmg, range, rate, radius, cost ─────────────────────
UDAT = {
    'mcv':          (600, 55,   0,   0, 0.0,  20, 3000),
    'infantry':     (100, 100,  20, 140, 1.5, 10,  100),
    'buggy':        (220, 130,  30, 160, 1.0, 13,  275),
    'tank':         (500, 200,  90, 220, 0.5, 17,  600),
    'rocket_tank':  (400, 195, 120, 300, 0.35, 17, 900),
    'tesla_tank':   (450, 180, 150, 180, 0.25, 17, 1100),
    'laser_tank':   (380, 216,  45, 260, 3.0,  17, 1000),
    'flame_tank':   (550, 186,  35, 120, 5.0,  17, 800),
    'harvester':    (350,  75,   0,   0, 0.0,  15, 1600),
}

# ── Building data: hp, w, h ───────────────────────────────────────────────────
BDAT = {
    'base':        (3000, 80, 80),
    'barracks':    ( 800, 56, 48),
    'factory':     (1200, 72, 56),
    'refinery':    (1000, 64, 56),
    'turret':      ( 600, 40, 40),
    'wall':        ( 300, 32, 32),
    'power_plant': ( 800, 56, 56),
}

TURRET_DMG, TURRET_RNG, TURRET_RATE = 60, 200, 0.8

CREDITS_START = 10000
TIB_VALUE     = 4        # credits per tib unit
HARVEST_RATE  = 45.0     # tib units/sec
HARVEST_CARRY = 200.0    # max tib carry

# AI timers
AI_BUILD_DT = 18.0
AI_RAID_DT  = 55.0
AI_RAID_N   = 7
AI_INCOME   = 40.0       # credits/sec passive income for enemy

# Production times (seconds)
PROD_TIME = {'infantry': 1.5, 'buggy': 2.5, 'tank': 3.5,
             'rocket_tank': 4.5, 'tesla_tank': 5.0,
             'laser_tank': 4.5, 'flame_tank': 4.0,
             'harvester': 4.0}

# Placeable building costs / build times
BUILD_COST = {'barracks': 800, 'factory': 2000, 'refinery': 2000, 'turret': 600, 'wall': 80, 'power_plant': 500}
BUILD_TIME = {'base': 2.0, 'barracks': 3.0, 'factory': 4.0, 'refinery': 4.0, 'turret': 2.0, 'wall': 0.5, 'power_plant': 2.5}

# Power demand per building type (completed buildings only)
POWER_DEMAND = {'turret': 10, 'factory': 20, 'barracks': 10, 'refinery': 15}
# Power plant output
POWER_OUTPUT = 100

# Influence radius per building (world pixels). Player can only build inside their influence.
INFLUENCE_RADIUS = {
    'base':        420,
    'barracks':    280,
    'factory':     280,
    'refinery':    240,
    'turret':      200,
    'wall':        120,
    'power_plant': 240,
}

# production menu per building type
PROD_MENU = {
    'barracks': ['infantry'],
    'factory':  ['buggy', 'tank', 'rocket_tank', 'tesla_tank',
                 'laser_tank', 'flame_tank', 'harvester'],
}

VISION_MULT = 1.6   # vision_radius = attack_range * VISION_MULT

# ── Tiberium spread ───────────────────────────────────────────────────────────
TIB_SPREAD_INTERVAL = 45.0   # seconds between spread ticks
TIB_SPREAD_CHANCE   = 0.25   # probability per field per tick
TIB_SPREAD_RADIUS   = 3      # tile radius to search for empty adjacent tiles
TIB_SPREAD_AMOUNT   = 200.0  # starting amount for a newly spawned field
TIB_MAX_FIELDS      = 80     # global cap on tiberium entities
TIB_DAMAGE_RATE     = 8.0    # hp/sec for unarmoured units standing on raw tib

# ── HUD tab layout (shared by render_sys + input_sys) ─────────────────────────
HUD_TAB_X   = 172    # x-start of tab strip
HUD_TAB_W   = 110    # width per tab header  (3 × 110 = 330 px)
HUD_TAB_H   = 22     # tab header height
HUD_BTN_W   = 80     # content button width
HUD_BTN_H   = 60     # content button height
HUD_BTN_GAP = 3      # gap between content buttons

# tab index → (display label, required completed building | None)
HUD_TABS = [
    ('STRUCTURES', 'base'),
    ('BARRACKS',   'barracks'),
    ('FACTORY',    'factory'),
]

# tab index → ordered list of buildable items
HUD_TAB_ITEMS = {
    0: ['barracks', 'factory', 'refinery', 'turret', 'wall', 'power_plant'],
    1: ['infantry'],
    2: ['buggy', 'tank', 'rocket_tank', 'tesla_tank',
        'laser_tank', 'flame_tank', 'harvester'],
}
