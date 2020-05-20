import logging
from sys import stderr

logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s: %(message)s',
    stream=stderr,
)

knxalog = logging.getLogger(__name__)
def log_async_exception(fun):
    @wraps(fun)
    async def wrapper(*args, **kwargs):
        try:
            return await fun(*args, **kwargs)
        except:
            knxalog.exception("Exception in %r:", fun.__qualname__)
            raise
    return wrapper

def setLogLevel(v):
    levels = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}
    level = v in levels and levels[v] or logging.CRITICAL
    knxalog.setLevel(level)

class BasePlugin:
    def __init__(self, daemon, cfg):
            self.d = daemon
            self.cfg = cfg
            self.device_name = cfg["name"]
            self.client = None
            self.obj_list = []
            default_hysteresis = "default_hysteresis" in self.cfg and self.cfg["default_hysteresis"] or 0
            for obj in cfg["objects"]:
                if obj["enabled"]:
                    obj.update({"value": 0})
                    if not "hysteresis" in obj:
                        obj.update({"hysteresis": default_hysteresis})
                    self.obj_list.append(obj)

    def _run(self):
        pass

    def run(self):
        if self.cfg["enabled"]:
            knxalog.info("running client for {}...".format(self.device_name))
            return self._run()

    def quit(self):
        if self.client:
            knxalog.info("quit client for {}...".format(self.device_name))
            self.client.close()

