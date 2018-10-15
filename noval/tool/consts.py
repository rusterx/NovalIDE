import wx

ID_MRU_FILE1 = wx.NewId()
ID_MRU_FILE2 = wx.NewId()
ID_MRU_FILE3 = wx.NewId()
ID_MRU_FILE4 = wx.NewId()
ID_MRU_FILE5 = wx.NewId()
ID_MRU_FILE6 = wx.NewId()
ID_MRU_FILE7 = wx.NewId()
ID_MRU_FILE8 = wx.NewId()
ID_MRU_FILE9 = wx.NewId()
ID_MRU_FILE10 = wx.NewId()
ID_MRU_FILE11 = wx.NewId()
ID_MRU_FILE12 = wx.NewId()
ID_MRU_FILE13 = wx.NewId()
ID_MRU_FILE14 = wx.NewId()
ID_MRU_FILE15 = wx.NewId()
ID_MRU_FILE16 = wx.NewId()
ID_MRU_FILE17 = wx.NewId()
ID_MRU_FILE18 = wx.NewId()
ID_MRU_FILE19 = wx.NewId()
ID_MRU_FILE20 = wx.NewId()


TEXT_VIEW = 1
IMAGE_VIEW = 2
HTML_WEB_VIEW = 3

SPACE = 10
HALF_SPACE = 5

_ = wx.GetTranslation

PYTHON_PATH_NAME = 'PYTHONPATH'
PROJECT_SHORT_EXTENSION = "nov"
PROJECT_EXTENSION = "." + PROJECT_SHORT_EXTENSION

PROJECT_NAMESPACE_URL = "noval"
DEFAULT_FILE_ENCODING_KEY = "DefaultFileEncoding"
NOT_IN_ANY_PROJECT = "Not in any Project"
#the first 2 line no of python file to place encoding declare
ENCODING_DECLARE_LINE_NUM = 2
DEFAULT_MRU_FILE_NUM = 9
ERROR_OK = 0
UNKNOWN_ERROR = -1

CHECK_UPDATE_ATSTARTUP_KEY = "CheckUpdateAtStartup"


DEFAULT_FONT_NAME = "Courier New"
DEFAULT_FONT_SIZE = 10
PRIMARY_FONT_KEY = "PrimaryFont"
SECONDARY_FONT_KEY = "SecondaryFont"

THEME_KEY = 'THEME'

DEFAULT_THEME_NAME = 'Default'

THEME_FILE_EXT = ".ess"
CHECK_EOL_KEY = "CheckEOL"

TEMPLATE_FILE_NAME = "template.xml"
USER_CACHE_DIR = "cache"


MIN_MRU_FILE_LIMIT = 1
MAX_MRU_FILE_LIMIT = 20

REMBER_FILE_KEY = "RemberFile"

FACE_ATTR_NAME =  "face"
FORE_ATTR_NAME =  "fore"
BACK_ATTR_NAME =  "back"
SIZE_ATTR_NAME =  "size"
EOL_ATTR_NAME  = "eol"
BOLD_ATTR_NAME = "bold"
ITALIC_ATTR_NAME = "italic"
UNDERLINE_ATTR_NAME = "underline"

GLOBAL_STYLE_NAME = "GlobalText"

DEFAULT_EDGE_GUIDE_WIDTH = 78

DEFAULT_DOCUMENT_TYPE_NAME = "Python Document"

#project or file property panel names
RESOURCE_ITEM_NAME = "Resource"
DEBUG_RUN_ITEM_NAME = "Debug/Run Settings"
INTERPRETER_ITEM_NAME = "Interpreter"
PYTHONPATH_ITEM_NAME = "PythonPath"
PROJECT_REFERENCE_ITEM_NAME = "Project References"