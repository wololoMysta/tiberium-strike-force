# systems/render_sys.py -- backward-compatible shim
# The real implementation now lives in systems/rendering/.
from systems.rendering.system import RenderSys
from systems.rendering import _cfg

# client.py patches these at runtime for team colouring
PLAYER = _cfg.PLAYER
ENEMY  = _cfg.ENEMY


def __getattr__(name):
    """Allow _rsys.PLAYER = x to propagate to _cfg."""
    if name == 'PLAYER':
        return _cfg.PLAYER
    if name == 'ENEMY':
        return _cfg.ENEMY
    raise AttributeError(name)

__all__ = ['RenderSys', 'PLAYER', 'ENEMY']
