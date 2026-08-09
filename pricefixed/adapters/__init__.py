"""Adapter registry. Add a source: drop a `SourceAdapter` subclass in this folder and
register it here. Keep the map alphabetical."""
from .appfolio import AppFolioAdapter
from .avalonbay import AvalonBayAdapter
from .brodsky import BrodskyAdapter
from .ccmanagers import CCManagersAdapter
from .corcoran import CorcoranSource
from .dermot import DermotAdapter
from .durst import DurstAdapter
from .elliman import EllimanSource
from .glenwood import GlenwoodAdapter
from .greystar import GreystarAdapter
from .lisamgmt import LisaManagementAdapter
from .manhattanskyline import ManhattanSkylineAdapter
from .nooklyn import NooklynAdapter
from .ogdencap import OgdenCapAdapter
from .olnick import OlnickAdapter
from .rockrose import RockroseAdapter
from .securecafe import SecureCafeAdapter
from .spherexx import SpherexxAdapter
from .stonehenge import StonehengeAdapter
from .stuytown import StuyTownAdapter
from .tfcornerstone import TFCornerstoneAdapter
from .udr import UDRAdapter

ADAPTERS = {
    a.name: a
    for a in (
        AppFolioAdapter,
        AvalonBayAdapter,
        BrodskyAdapter,
        CCManagersAdapter,
        CorcoranSource,
        DermotAdapter,
        DurstAdapter,
        EllimanSource,
        GlenwoodAdapter,
        GreystarAdapter,
        LisaManagementAdapter,
        ManhattanSkylineAdapter,
        NooklynAdapter,
        OgdenCapAdapter,
        OlnickAdapter,
        RockroseAdapter,
        SecureCafeAdapter,
        SpherexxAdapter,
        StonehengeAdapter,
        StuyTownAdapter,
        TFCornerstoneAdapter,
        UDRAdapter,
    )
}
