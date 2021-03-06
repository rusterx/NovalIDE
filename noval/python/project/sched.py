# -*- coding: utf-8 -*-
from noval import GetApp,_
import os
import sys
import time
import threading
import noval.python.parser.utils as parserutils
import noval.util.strutils as strutils
import noval.python.parser.fileparser as fileparser
import datetime
import pickle
import noval.util.apputils as sysutilslib
import noval.util.utils as utils
import glob
import noval.util.fileutils as fileutils

class SchedulerRun(threading.Thread):
    '''
        生成项目代码的智能提示数据库,每隔一段时间执行
    '''
    
    INTERVAL_TIME_SECOND = 3
    UPDATE_FILE = 'update.time'
    
    def __init__(self,proj):
        #设置为后台线程,防止退出程序时卡死
        threading.Thread.__init__(self,daemon=True)
        self._is_parsing = False
        self.last_update_time = -1
        self._proj = proj

    def run(self):
        self.watch_project()
        
    def watch_project(self):
        doc = self._proj
        if doc != None:
            self.parse_project(doc)
            #解析引用项目的代码
            ref_project_docs = GetApp().MainFrame.GetProjectView(generate_event=False).GetReferenceProjects(doc,ensure_open=True)
            for document in ref_project_docs:
                self.parse_project(document)

            
    def get_last_update(self,intellisence_data_path):
        update_file_path = os.path.join(intellisence_data_path,self.UPDATE_FILE)
        if not os.path.exists(update_file_path):
            return 0
        else:
            return self.load_last_update(intellisence_data_path)

    def load_last_update(self,intellisence_data_path):
        time_stamp = 0
        update_file_path = os.path.join(intellisence_data_path,self.UPDATE_FILE)
        with open(update_file_path,"rb") as f:
            try:
                date_list = pickle.load(f)
                time_stamp = date_list[0]
            except:
                utils.get_logger().error('load update time file %s fail',update_file_path)
                return 0
        return time_stamp
                
    def update_last_time(self,intellisence_data_path):
        update_datetime = datetime.datetime.now()
        time_stamp = time.mktime(update_datetime.timetuple())
        tm = [time_stamp]
        update_file_path = os.path.join(intellisence_data_path,self.UPDATE_FILE)
        with open(update_file_path,"wb") as f:
            pickle.dump(tm,f)

    def parse_project(self,doc):
        doc.UpdateData([])
        assert (doc != None)
        project = doc.GetModel()
        project_location = os.path.dirname(doc.GetFilename())
        path_list = [project_location]
        intellisence_data_path = doc.GetDataPath()
        self.last_update_time = self.get_last_update(intellisence_data_path)
        if not os.path.exists(intellisence_data_path):
            parserutils.MakeDirs(intellisence_data_path)
            #hidden intellisence data path on windows and linux
            if sysutilslib.is_windows():
                import win32api
                import win32con
                win32api.SetFileAttributes(intellisence_data_path, win32con.FILE_ATTRIBUTE_HIDDEN)
        
        update_file_count = 0
        all_modules = []
        for filepath in project.filePaths:
            if not os.path.exists(filepath):
                continue
            file_dir = os.path.dirname(filepath)
            is_package_dir = fileparser.is_package_dir(file_dir)
            if is_package_dir or parserutils.PathsContainPath(path_list,file_dir):
                ext = strutils.get_file_extension(filepath)
                if ext in ['py','pyw']:
                    mk_time = os.path.getmtime(filepath)
                    relative_module_name,is_package = parserutils.get_relative_name(filepath,path_list)
                    all_modules.append(relative_module_name)
                    is_new_module = not os.path.exists(os.path.join(intellisence_data_path,relative_module_name + ".$members"))
                    if mk_time > self.last_update_time or is_new_module:
                        utils.get_logger().debug('update file %s ,relative module name is %s,%d,%d,%d',filepath,relative_module_name,mk_time, self.last_update_time , is_new_module)
                        file_parser = fileparser.FiledumpParser(filepath,intellisence_data_path,force_update=True,path_list=path_list)
                        suc = file_parser.Dump()
                        if suc:
                            update_file_count += 1
                            utils.update_statusbar(_("updating intellisense of file \"%s\"")%filepath)
                            #新添加包则需要更新父包的子模块信息
                            if is_package or is_new_module:
                                parent_dir = os.path.dirname(os.path.dirname(file_dir))
                                if fileparser.is_package_dir(parent_dir):
                                    parent_package_file_path = os.path.join(parent_dir,"__init__.py")
                                    file_parser = fileparser.FiledumpParser(parent_package_file_path,intellisence_data_path,force_update=True,path_list=path_list)
                                    file_parser.Dump()
                                    update_file_count += 1
                                    utils.update_statusbar(_("updating intellisense of file \"%s\"")%parent_package_file_path)
                                #新添加子模块则需要更新包的子模块信息
                                elif is_new_module and is_package_dir:
                                    package_file_path = os.path.join(file_dir,"__init__.py")
                                    file_parser = fileparser.FiledumpParser(package_file_path,intellisence_data_path,force_update=True,path_list=path_list)
                                    file_parser.Dump()
                                    update_file_count += 1
                                    utils.update_statusbar(_("updating intellisense of file \"%s\"")%package_file_path)
            else:
                utils.get_logger().debug('%s is not valid parse dir',file_dir)
        utils.get_logger().debug('total update %d files',update_file_count)
        if update_file_count > 0:
            self.update_last_time(intellisence_data_path)
        doc.UpdateData(all_modules)
        utils.update_statusbar(_("Ready"))

class ProjectDatabaseLoader:
    def __init__(self,doc):
        self.module_dicts = {}
        self.import_list = []
        self.doc = doc
        
    def LoadMetadata(self,all_modules=[]):
        meta_data_path = self.doc.GetDataPath()
        if not os.path.exists(meta_data_path):
            return
        self.module_dicts.clear()
        name_sets = set()
        for filepath in glob.glob(os.path.join(meta_data_path,"*.$members")):
            filename = os.path.basename(filepath)
            module_name = '.'.join(filename.split(".")[0:-1])
            if all_modules and not module_name in all_modules:
                utils.get_logger().warn('module name %s is not exist again,remove members file....',module_name)
                fileutils.safe_remove(filepath)
                fileutils.safe_remove(os.path.join(meta_data_path,module_name+".$memberlist"))
                continue
            name_sets.add(module_name)
        for name in name_sets:
            d = dict(members=os.path.join(meta_data_path,name +".$members"),\
                     member_list=os.path.join(meta_data_path,name +".$memberlist"))
            self.module_dicts[name] = d
        self.LoadImportList()
        
        #加载引用项目的智能提示数据
        ref_project_docs = GetApp().MainFrame.GetProjectView(generate_event=False).GetReferenceProjects(self.doc,ensure_open=True)
        for document in ref_project_docs:
            ref_doc = ProjectDatabaseLoader(document)
            ref_doc.LoadMetadata()
            self.module_dicts.update(ref_doc.module_dicts)
            self.import_list.append(ref_doc.import_list)

    def LoadImportList(self):
        self.import_list = []
        for key in self.module_dicts.keys():
            if key.find(".") == -1:
                self.import_list.append(key)
    