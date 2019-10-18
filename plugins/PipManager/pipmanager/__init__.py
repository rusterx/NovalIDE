# -*- coding: utf-8 -*-
from noval import _,GetApp,NewId
import noval.iface as iface
import noval.plugin as plugin
import noval.util.utils as utils
import noval.constants as constants
from dummy.userdb import UserDataDb
import os
from noval.python.plugins.pip_gui import *
import threading

class PipManagerPlugin(plugin.Plugin):
    """Simple Programmer's Calculator"""
    plugin.Implements(iface.MainWindowI)
    
    PACKAGE_FILE_NAME = "pypi_packages.txt"
    PACKAGE_COUNT_FILE_NAME = "pypi_packages_count.txt"
    ID_PIP_GUI = NewId()
    def PlugIt(self, parent):
        """Hook the calculator into the menu and bind the event"""
        utils.get_logger().info("Installing PipManager plugin")
        self.parent = parent
        self.message = {'msg':_("fetching package from PyPI.......")}
        t = threading.Thread(target=self.GetAllPackages)
        #daemon表示后台线程,即程序不用等待子线程才退出
        t.daemon = True
        t.start()
        GetApp().InsertCommand(constants.ID_OPEN_TERMINAL,self.ID_PIP_GUI,_("&Tools"),_("Manage packages..."),handler=self.ShowPipDlg,pos="before")

    def GetAllPackages(self):
        api_addr = '%s/member/get_pypi_packages' % (UserDataDb.HOST_SERVER_ADDR)
        data = utils.RequestData(api_addr,method='get')
        if data is None:
            self.message = {'msg':_("can't fetch package from PyPI")}
            return
        names = data['names']
        utils.get_logger().info('get total %d packages from server',len(names))
        package_data_path,package_data_count_path = self.GetPacakgeDataPath()
        with open(package_data_path,"w") as f:
            f.write('\n'.join(names))
            
        with open(package_data_count_path,"w") as f:
            f.write(str(len(names)))
        self.message = {'msg':_("fetch package from PyPI success")}

    def GetPacakgeDataPath(self):
        app_data_path = utils.get_user_data_path()
        package_data_path = os.path.join(app_data_path,"cache",self.PACKAGE_FILE_NAME)
        return package_data_path,os.path.join(app_data_path,"cache",self.PACKAGE_COUNT_FILE_NAME)
        
    def GetAllPackagesCount(self):
        package_data_path,package_data_count_path = self.GetPacakgeDataPath()
        if not os.path.exists(package_data_count_path):
            return 0
        with open(package_data_count_path,) as f:
            return int(f.read())
        return 0

    def ShowPipDlg(self):
        package_count = self.GetAllPackagesCount()
        pip_dlg = PyPiPipDialog(self.parent,package_count=package_count,message=self.message)
        pip_dlg.ShowModal()