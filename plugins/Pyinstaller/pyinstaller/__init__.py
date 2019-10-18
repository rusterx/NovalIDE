###############################################################################
# Name: __init__.py                                                           #
# Purpose: Simple Calculator Plugin                                           #
# Author: Cody Precord <cprecord@editra.org>                                  #

"""Simple Programmer's Calculator"""
__author__ = "Cody Precord"
__version__ = "0.6"

#-----------------------------------------------------------------------------#
from noval import _,GetApp,NewId
import noval.iface as iface
import noval.plugin as plugin
import noval.util.utils as utils
import noval.constants as constants
from noval.project.templatemanager import ProjectTemplateManager
from noval.project.debugger import OutputRunCommandUI
from noval.python.debugger.output import *
from noval.project.baseconfig import *
import noval.python.debugger.debugger as pythondebugger
import noval.consts as consts
import noval.util.fileutils as fileutils

# Local imports
import pyinstaller.pyinstall as pyinstall
#-----------------------------------------------------------------------------#

# Try and add this plugins message catalogs to the app

#wx.GetApp().AddMessageCatalog('calculator', __name__)
#-----------------------------------------------------------------------------#

class OutputView(OutputRunCommandUI):
    
    ID_PYINSTALLER_DEBUG = NewId()
    ID_PYINSTALLER_CONFIG = NewId()
    def __init__(self,master):
        GetApp()._debugger_class = pythondebugger.PythonDebugger
        OutputRunCommandUI.__init__(self,master,GetApp().GetDebugger())
        GetApp().bind(constants.PROJECTVIEW_POPUP_FILE_MENU_EVT, self.AppenFileMenu,True)
        GetApp().bind(constants.PROJECTVIEW_POPUP_ROOT_MENU_EVT, self.AppenRootMenu,True)
        
    def AppenRootMenu(self, event):
         menu = event.get('menu')
         menu.add_separator()
         menu.Append(self.ID_PYINSTALLER_DEBUG,_("&Convert to exe by Pyinstaller"),handler=None) 
         menu.Append(self.ID_PYINSTALLER_CONFIG,_("Pyinstaller Configuration"),handler=None)

    def AppenFileMenu(self, event):
         menu = event.get('menu')
         tree_item = event.get('item')
         project_browser = GetApp().MainFrame.GetView(consts.PROJECT_VIEW_NAME)
         filePath = project_browser.GetView()._GetItemFilePath(tree_item)
         if project_browser.GetView()._IsItemFile(tree_item) and fileutils.is_python_file(filePath):
            menu.add_separator()
            menu.Append(self.ID_PYINSTALLER_DEBUG,_("&Convert to exe by Pyinstaller"),handler=None)
            menu.Append(self.ID_PYINSTALLER_CONFIG,_("Pyinstaller Configuration"),handler=None)

    def ExecutorFinished(self,stopped=True):
        OutputRunCommandUI.ExecutorFinished(self,stopped=stopped)
        if not self._stopped:
            target_exe_path = self._run_parameter.GetTargetPath()
            print ('target exe path is',target_exe_path)
            view = GetApp().MainFrame.GetCommonView("Output")
            view.GetOutputview().SetTraceLog(True)
            run_parameter = BaseRunconfig(target_exe_path)
            view._textCtrl.ClearOutput()
            view.SetRunParameter(run_parameter)
            view.CreateExecutor()
            view.Execute()

    def GetOuputctrlClass(self):
        return DebugOutputctrl

class Pyinstaller(plugin.Plugin):
    """Simple Programmer's Calculator"""
    plugin.Implements(iface.MainWindowI)
    def PlugIt(self, parent):
        """Hook the calculator into the menu and bind the event"""
        utils.get_logger().info("Installing pyinstaller plugin")
        ProjectTemplateManager().AddProjectTemplate("Python/Pyinstaller",_("Console Application"),[pyinstall.PyinstallerProjectNameLocationPage,pyinstall.PyinstallerDubugrunConfigurationPage,\
                        ("noval.project.importfiles.ImportfilesPage",{'rejects':[]})])
        ProjectTemplateManager().AddProjectTemplate("Python/Pyinstaller",_("Windows Application"),[pyinstall.PyinstallerProjectNameLocationPage,pyinstall.PyinstallerDubugrunConfigurationPage,\
                        ("noval.project.importfiles.ImportfilesPage",{'rejects':[]})])
        ProjectTemplateManager().AddProjectTemplate("Python/Pyinstaller",_("A simple helloworld demo"),[pyinstall.PyinstallerProjectNameLocationPage,pyinstall.PyinstallerDubugrunConfigurationPage,"noval.xx"])

 
        GetApp().MainFrame.AddView("Output",OutputView, _("Output"), "s",image_file="search.ico")