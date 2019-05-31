# -*- coding: utf-8 -*-
#-------------------------------------------------------------------------------
# Name:        baseviewer.py
# Purpose:
#
# Author:      wukan
#
# Created:     2019-02-15
# Copyright:   (c) wukan 2019
# Licence:     GPL-3.0
#-------------------------------------------------------------------------------
from noval import GetApp,_
import noval.core as core
import tkinter as tk
from tkinter import ttk,messagebox,filedialog
import copy
import os
import os.path
#import sets
import sys
import time
import types
import noval.util.appdirs as appdirs
import noval.util.strutils as strutils
import noval.util.fileutils as fileutils
import noval.util.logger as logger
import noval.project.basemodel as projectlib
import noval.util.apputils as sysutilslib
import shutil
import noval.python.parser.utils as parserutils
##import ProjectUI
#from noval.model import configuration
import uuid
import noval.filewatcher as filewatcher
import pickle
#import NewFile
#import noval.tool.debugger.DebuggerService as DebuggerService
import datetime
from noval.util import utils
#import Property
#import noval.tool.project.RunConfiguration as RunConfiguration
import noval.constants as constants
import noval.consts as consts
import noval.project.Wizard as Wizard
import noval.imageutils as imageutils
import noval.project.baserun as baserun
import noval.project.command as projectcommand
from noval.project.templatemanager import ProjectTemplateManager
import noval.newTkDnD as newTkDnD
import noval.misc as misc
import noval.ui_base as ui_base
import noval.ui_utils as ui_utils
    
#----------------------------------------------------------------------------
# Constants
#----------------------------------------------------------------------------

PROJECT_KEY = "/NOV_Projects"
PROJECT_DIRECTORY_KEY = "NewProjectDirectory"

NEW_PROJECT_DIRECTORY_DEFAULT = appdirs.getSystemDir()
#DF_COPY_FILENAME = wx.CustomDataFormat("copy_file_names")

#添加项目文件覆盖已有文件时默认处理方式
DEFAULT_PROMPT_MESSAGE_ID = constants.ID_YES

def getProjectKeyName(projectId):
    return "%s/{%s}/%s" % (PROJECT_KEY, projectId, "OpenFolders")

#----------------------------------------------------------------------------
# Classes
#----------------------------------------------------------------------------

class ProjectDocument(core.Document):
    
    UNPROJECT_MODEL_ID = "8F470CCF-A44F-11E8-88DC-005056C00008"
    #项目生成的二进制文件不能添加到项目中去
    BIN_FILE_EXTS = []
    
    @classmethod
    def GetUnProjectDocument(cls):
        unproj_model = cls.GetProjectModel()
        unproj_model.Id = ProjectDocument.UNPROJECT_MODEL_ID
        unprojProj = ProjectDocument(model=unproj_model)
        unprojProj.SetFilename(consts.NOT_IN_ANY_PROJECT)
        return unprojProj
        
    @staticmethod
    def GetUnProjectFileKey(file_path,lastPart):
        return "%s/{%s}/%s/%s" % (PROJECT_KEY, ProjectDocument.UNPROJECT_MODEL_ID, file_path.replace(os.sep, '|'),lastPart)


    def __init__(self, model=None):
        core.Document.__init__(self)
        if model:
            self.SetModel(model)
        else:
            self.SetModel(self.GetProjectModel())  # initial model used by "File | New... | Project"
        self._stageProjectFile = False
        self._run_parameter = None
        self.document_watcher = filewatcher.FileAlarmWatcher()
        self._commandProcessor = projectcommand.CommandProcessor()
        
    @staticmethod
    def GetProjectModel():
        raise Exception("This method must be implemented in derived class")

    def GetRunConfiguration(self,start_up_file):
        file_key = self.GetFileKey(start_up_file)
        run_configuration_name = utils.ProfileGet(file_key + "/RunConfigurationName","")
        return run_configuration_name
    
    def __copy__(self):
        model = copy.copy(self.GetModel())        
        clone =  ProjectDocument(model)
        clone.SetFilename(self.GetFilename())
        return clone

    def GetFirstView(self):
        """ Bug: workaround.  If user tries to open an already open project with main menu "File | Open...", docview.DocManager.OnFileOpen() silently returns None if project is already open.
            And to the user, it appears as if nothing has happened.  The user expects to see the open project.
            This forces the project view to show the correct project.
        """
        view = core.Document.GetFirstView(self)
        view.SetProject(self.GetFilename())  # ensure project is displayed in view
        return view

    def GetModel(self):
        return self._projectModel

    def GetPath(self):
        return os.path.dirname(self.GetFilename())

    def SetModel(self, model):
        self._projectModel = model
        
    def GetKey(self,lastPart=None):
        if not lastPart:
            return "%s/{%s}" % (PROJECT_KEY, self.GetModel().Id)
        return "%s/{%s}/%s" % (PROJECT_KEY, self.GetModel().Id, lastPart)
        
    def GetFileKey(self,pj_file,lastPart=None):
        if pj_file.logicalFolder is None:
            key_path = os.path.basename(pj_file.filePath)
        else:
            key_path = os.path.join(pj_file.logicalFolder,os.path.basename(pj_file.filePath))
        key_path = fileutils.opj(key_path)
        if lastPart is None:
           return "%s/{%s}/%s" % (PROJECT_KEY, self.GetModel().Id, key_path.replace(os.sep, '|')) 
        return "%s/{%s}/%s/%s" % (PROJECT_KEY, self.GetModel().Id, key_path.replace(os.sep, '|'),lastPart)

    def OnCreate(self, path, flags):
        view = GetApp().MainFrame.GetProjectView().GetView()
        # All project documents share the same view.
        self.AddView(view)
        return view

    def LoadObject(self, fileObject):
        self.SetModel(projectlib.load(fileObject))
      #  self.GetModel().SetDocCallback(GetDocCallback)
        return True


    def SaveObject(self, fileObject):
        projectlib.save(fileObject, self.GetModel())
##        try:
##            projectlib.save(fileObject, self.GetModel())
##        except Exception as e:
##            wx.MessageBox(_("Project %s Save Failed") % self.GetModel().Name,_("Save Project"),wx.OK|wx.ICON_ERROR,wx.GetApp().GetTopWindow())
##            return False
        return True

    def OnOpenDocument(self, filePath):
        view = GetApp().MainFrame.GetProjectView(show=True,generate_event=False).GetView()
        if not os.path.exists(filePath):
            GetApp().CloseSplash()
            msgTitle = GetApp().GetAppName()
            if not msgTitle:
                msgTitle = _("File Error")
            messagebox.showwarning(msgTitle,_("Could not find '%s'.") % filePath,parent = GetApp().GetTopWindow())
            #TODO:this may cause problem ,should watch some time to check error or not
            if self in self.GetDocumentManager().GetDocuments():
                self.Destroy()
            return True  # if we return False, the Project View is destroyed, Service windows shouldn't be destroyed

        fileObject = open(filePath, 'r')
        try:
            self.LoadObject(fileObject)
        except Exception as e:
            GetApp().CloseSplash()
            msgTitle = GetApp().GetAppName()
            if not msgTitle:
                msgTitle = _("File Error")
            messagebox.showerror(msgTitle,_("Could not open '%s'.  %s") % (fileutils.get_filename_from_path(filePath), e))
            #TODO:this may cause problem ,should watch some time to check effection
            if self in self.GetDocumentManager().GetDocuments():
                self.Destroy()
            return True  # if we return False, the Project View is destroyed, Service windows shouldn't be destroyed

        project_obj = self.GetModel()
        #to make compatible to old version,which old project instance has no id attr
        if project_obj.id == '':
            project_obj.id = str(uuid.uuid1()).upper()
            self.Modify(True)
        else:
            self.Modify(False)
        self.SetFilename(filePath, True)
        view.AddProjectToView(self)
        self.SetDocumentModificationDate()
        self.UpdateAllViews()
        self._savedYet = True
        view.Activate()
        self.document_watcher.AddFileDoc(self)
        return True

    def OnSaveDocument(self, filename):
        self.document_watcher.StopWatchFile(self)
        suc = core.Document.OnSaveDocument(self,filename)
        self.document_watcher.StartWatchFile(self)
        return suc

    def AddFile(self, filePath, folderPath=None, type=None, name=None):
        if type:
            types = [type]
        else:
            types = None
        if name:
            names = [name]
        else:
            names = None
            
        return self.AddFiles([filePath], folderPath, types, names)


    def AddFiles(self, filePaths=None, folderPath=None, types=None, names=None, files=None):
        # Filter out files that are not already in the project
        if filePaths:
            newFilePaths = []
            oldFilePaths = []
            for filePath in filePaths:
                if self.GetModel().FindFile(filePath):
                    oldFilePaths.append(filePath)
                else:
                    newFilePaths.append(filePath)
    
            for i, filePath in enumerate(newFilePaths):
                if types:
                    type = types[i]
                else:
                    type = None
                    
                if names:
                    name = names[i]
                else:
                    name = None
                    
                if not folderPath:
                    folder = None
                else:
                    folder = folderPath
                    
                #不要添加二进制文件到项目中去
                if strutils.get_file_extension(filePath) in self.BIN_FILE_EXTS:
                    continue
                self.GetModel().AddFile(filePath, folder, type, name)
        elif files:
            newFilePaths = []
            oldFilePaths = []
            for file in files:
                if self.GetModel().FindFile(file.filePath):
                    oldFilePaths.append(file.filePath)
                else:
                    newFilePaths.append(file.filePath)
                    self.GetModel().AddFile(file=file)
        else:
            return False
                
        self.UpdateAllViews(hint = (consts.PROJECT_ADD_COMMAND_NAME, self, newFilePaths, oldFilePaths))
        if len(newFilePaths):
            self.Modify(True)
            return True
        else:
            return False
            
    def AddProgressFiles(self,progress_ui,filePaths=None, folderPath=None, types=None, names=None,range_value = 0):
        # Filter out files that are not already in the project
        if filePaths:
            newFilePaths = []
            oldFilePaths = []
            for filePath in filePaths:
                if self.GetModel().FindFile(filePath):
                    oldFilePaths.append(filePath)
                    range_value += 1
                    wx.CallAfter(Publisher.sendMessage, ImportFiles.NOVAL_MSG_UI_IMPORT_FILES_PROGRESS, \
                             value=range_value,is_cancel=self.GetFirstView().IsStopImport)
                else:
                    newFilePaths.append(filePath)
    

            for i, filePath in enumerate(newFilePaths):
                if types:
                    type = types[i]
                else:
                    type = None
                    
                if names:
                    name = names[i]
                else:
                    name = None
                    
                if not folderPath:
                    folder = projectService.FindLogicalViewFolderDefault(filePath)
                else:
                    folder = folderPath
                #禁止二进制文件类型禁止添加到项目中
                if strutils.get_file_extension(filePath) in self.BIN_FILE_EXTS:
                    continue
                self.GetModel().AddFile(filePath, folder, type, name)
        else:
            return False

        self.UpdateAllViews(hint = (consts.PROJECT_ADD_PROGRESS_COMMAND_NAME, self, newFilePaths,range_value,progress_ui))
        if len(newFilePaths):
            self.Modify(True)
            return True
        else:
            return False


    def RemoveFile(self, filePath):
        return self.RemoveFiles([filePath])


    def RemoveFiles(self, filePaths=None, files=None):
        removedFiles = []
        
        if files:
            filePaths = []
            for file in files:
                filePaths.append(file.filePath)
                  
        for filePath in filePaths:
            file = self.GetModel().FindFile(filePath)
            if file:
                self.GetModel().RemoveFile(file)
                removedFiles.append(file.filePath)
                                        
        self.UpdateAllViews(hint = ("remove", self, removedFiles))
        if len(removedFiles):
            self.Modify(True)
            return True
        else:
            return False


    def RenameFile(self, oldFilePath, newFilePath, isProject = False):
        try:
            if oldFilePath == newFilePath:
                return False
            openDoc = None
            # projects don't have to exist yet, so not required to rename old file,
            # but files must exist, so we'll try to rename and allow exceptions to occur if can't.
            if not isProject or (isProject and os.path.exists(oldFilePath)):
                openDoc = self.GetFirstView().GetOpenDocument(oldFilePath)
                if openDoc:
                    openDoc.FileWatcher.StopWatchFile(openDoc)
                os.rename(oldFilePath, newFilePath)
            if isProject:
                documents = self.GetDocumentManager().GetDocuments()
                for document in documents:
                    if os.path.normcase(document.GetFilename()) == os.path.normcase(oldFilePath):  # If the renamed document is open, update it
                        document.SetFilename(newFilePath)
                        document.SetTitle(wx.lib.docview.FileNameFromPath(newFilePath))
                        document.UpdateAllViews(hint = ("rename", self, oldFilePath, newFilePath))
            else:
                self.UpdateFilePath(oldFilePath, newFilePath)
                if openDoc:
                    openDoc.SetFilename(newFilePath, notifyViews = True)
                    openDoc.UpdateAllViews(hint = ("rename", self, oldFilePath, newFilePath))
                    openDoc.FileWatcher.StartWatchFile(openDoc)
                    ###openDoc.GetFirstView().DoLoadOutlineCallback(True)

            return True
        except OSError as e:
            msgTitle = _("Rename File Error")
            messagebox.showerror(msgTitle,_("Could not rename file '%s'.  '%s'") % (fileutils.get_filename_from_path(oldFilePath), e),
                          parent=GetApp().GetTopWindow())
            return False


    def MoveFile(self, file, newFolderPath):
        return self.MoveFiles([file], newFolderPath)


    def MoveFiles(self, files, newFolderPath):
        filePaths = []
        newFilePaths = []
        move_files = []
        isArray = isinstance(newFolderPath, type([]))
        for i in range(len(files)):
            if isArray:
                files[i].logicalFolder = newFolderPath[i]
            else:
                files[i].logicalFolder = newFolderPath
            oldFilePath = files[i].filePath
            filename = os.path.basename(oldFilePath)
            if isArray:
                destFolderPath = newFolderPath[i]
            else:
                destFolderPath = newFolderPath
            newFilePath = os.path.join(self.GetModel().homeDir,\
                                destFolderPath,filename)
            #this is the same file,which will ignore
            if parserutils.ComparePath(oldFilePath,newFilePath):
                continue
            if os.path.exists(newFilePath):
                ret = wx.MessageBox(_("Dest file is already exist,Do you want to overwrite it?"),_("Move File"),\
                                  wx.YES_NO|wx.ICON_QUESTION,self.GetFirstView()._GetParentFrame())
                if ret == wx.NO:
                    continue        
            try:
                shutil.move(oldFilePath,newFilePath)
            except Exception as e:
                wx.MessageBox(str(e),style = wx.OK|wx.ICON_ERROR)
                return False
            filePaths.append(oldFilePath)
            newFilePaths.append(newFilePath)
            move_files.append(files[i])

        self.UpdateAllViews(hint = ("remove", self, filePaths))
        for k in range(len(move_files)):
            move_files[k].filePath = newFilePaths[k]
        self.UpdateAllViews(hint = ("add", self, newFilePaths, []))
        self.Modify(True)
        return True


    def UpdateFilePath(self, oldFilePath, newFilePath):
        file = self.GetModel().FindFile(oldFilePath)
        self.RemoveFile(oldFilePath)
        if file:
            self.AddFile(newFilePath, file.logicalFolder, file.type, file.name)
        else:
            self.AddFile(newFilePath)


    def RemoveInvalidPaths(self):
        """Makes sure all paths project knows about are valid and point to existing files. Removes and returns list of invalid paths."""

        invalidFileRefs = []
        
        fileRefs = self.GetFileRefs()
        
        for fileRef in fileRefs:
            if not os.path.exists(fileRef.filePath):
                invalidFileRefs.append(fileRef)

        for fileRef in invalidFileRefs:
            fileRefs.remove(fileRef)

        return [fileRef.filePath for fileRef in invalidFileRefs]


    def SetStageProjectFile(self):
        self._stageProjectFile = True


    def ArchiveProject(self, zipdest):
        """Zips stagedir, creates a zipfile that has as name the projectname, in zipdest. Returns path to zipfile."""
        if os.path.exists(zipdest):
            raise AssertionError("Cannot archive project, %s already exists" % zipdest)
        fileutils.zip(zipdest, files=self.GetModel().filePaths)
        return zipdest


    def StageProject(self, tmpdir, targetDataSourceMapping={}):
        """ Copies all files this project knows about into staging location. Files that live outside of the project dir are copied into the root of the stage dir, and their recorded file path is updated. Files that live inside of the project dir keep their relative path. Generates .dpl file into staging dir. Returns path to staging dir."""

        projname = self.GetProjectName()
        stagedir = os.path.join(tmpdir, projname)
        fileutils.remove(stagedir)
        os.makedirs(stagedir)        

        # remove invalid files from project
        self.RemoveInvalidPaths()        

        # required so relative paths are written correctly when .dpl file is
        # generated below.
        self.SetFilename(os.path.join(stagedir,
                                      os.path.basename(self.GetFilename())))
        projectdir = self.GetModel().homeDir

        # Validate paths before actually copying, and populate a dict
        # with src->dest so copying is easy.
        # (fileDict: ProjectFile instance -> dest path (string))
        fileDict = self._ValidateFilePaths(projectdir, stagedir)
        
        # copy files to staging dir
        self._StageFiles(fileDict)

        # set target data source for schemas
        self._SetSchemaTargetDataSource(fileDict, targetDataSourceMapping)

        # it is unfortunate we require this. it would be nice if filepaths
        # were only in the project
        self._FixWsdlAgFiles(stagedir)
            
        # generate .dpl file
        dplfilename = projname + deploymentlib.DEPLOYMENT_EXTENSION
        dplfilepath = os.path.join(stagedir, dplfilename)
        self.GenerateDeployment(dplfilepath)

        if self._stageProjectFile:
            # save project so we get the .agp file. not required for deployment
            # but convenient if user wants to open the deployment in the IDE
            agpfilename = projname + PROJECT_EXTENSION
            agpfilepath = os.path.join(stagedir, agpfilename)

            # if this project has deployment data sources configured, remove
            # them. changing the project is fine, since this is a clone of
            # the project the IDE has.
            self.GetModel().GetAppInfo().ResetDeploymentDataSources()
            
            f = None
            try:
                f = open(agpfilepath, "w")
                
                # setting homeDir correctly is required for the "figuring out
                # relative paths" logic when saving the project
                self.GetModel().homeDir = stagedir
                
                projectlib.save(f, self.GetModel(), productionDeployment=True)
            finally:
                try:
                    f.close()
                except: pass

        return stagedir
        
    def _StageFiles(self, fileDict):
        """Copy files to staging directory, update filePath attr of project's ProjectFile instances."""

        # fileDict: ProjectFile instance -> dest path (string)
        
        for fileRef, fileDest in fileDict.items():
            fileutils.copyFile(fileRef.filePath, fileDest)
            fileRef.filePath = fileDest

    def _ValidateFilePaths(self, projectdir, stagedir):
        """If paths validate, returns a dict mapping ProjectFile to destination path. Destination path is the path the file needs to be copied to for staging. If paths don't validate, throws an IOError.
           With our current slightly simplistic staging algorithm, staging will not work iff the project has files outside of the projectdir with names (filename without path) that:
             -  match filenames of files living at the root of the project.
             -  are same as those of any other file that lives outside of the projectdir.
          
           We have this limitation because we move any file that lives outside of the project dir into the root of the stagedir (== copied project dir). We could make this smarter by either giving files unique names if we detect a collistion, or by creating some directory structure instead of putting all files from outside of the projectdir into the root of the stagedir (== copied projectdir)."""

        # ProjectFile instance -> dest path (string)
        rtn = {}
        
        projectRootFiles = sets.Set()   # live at project root
        foreignFiles = sets.Set()       # live outside of project

        fileRefsToDeploy = self.GetFileRefs()

        for fileRef in fileRefsToDeploy:
            relPath = fileutils.getRelativePath(fileRef.filePath, projectdir)
            filename = os.path.basename(fileRef.filePath)            
            if not relPath: # file lives outside of project dir...

                # do we have another file with the same name already?
                if filename in foreignFiles:
                    raise IOError("More than one file with name \"%s\" lives outside of the project. These files need to have unique names" % filename)
                foreignFiles.add(filename)       
                fileDest = os.path.join(stagedir, filename)
            else:
                # file lives somewhere within the project dir
                fileDest = os.path.join(stagedir, relPath)
                if not os.path.dirname(relPath):
                    projectRootFiles.add(filename)
                
            rtn[fileRef] = fileDest

        # make sure we won't collide with a file that lives at root of
        # projectdir when moving files into project
        for filename in foreignFiles:
            if filename in projectRootFiles:
                raise IOError("File outside of project, \"%s\", cannot have same name as file at project root" % filename)
        return rtn
    
                            
    def RenameFolder(self, oldFolderLogicPath, newFolderLogicPath):
        try:
            oldFolderPath = os.path.join(self.GetModel().homeDir,oldFolderLogicPath)
            newFolderPath = os.path.join(self.GetModel().homeDir,newFolderLogicPath)
            os.rename(oldFolderPath, newFolderPath)
        except Exception as e:
            messagebox.showerror(_("Rename Folder Error"),_("Could not rename folder '%s'.  '%s'") % (fileutils.get_filename_from_path(oldFolderPath), e),parent= GetApp().GetTopWindow())
            return False
        rename_files = []
        for file in self.GetModel()._files:
            if file.logicalFolder == oldFolderLogicPath:
                file.logicalFolder = newFolderLogicPath
                oldFilePath = file.filePath
                file_name = os.path.basename(oldFilePath)
                newFilePath = os.path.join(newFolderPath,file_name)
                rename_files.append((oldFilePath,newFilePath))
        for rename_file in rename_files:
            oldFilePath, newFilePath = rename_file
            self.UpdateFilePath(oldFilePath, newFilePath)
            openDoc = self.GetFirstView().GetOpenDocument(oldFilePath)
            if openDoc:
                openDoc.SetFilename(newFilePath, notifyViews = True)
                openDoc.UpdateAllViews(hint = ("rename", self, oldFilePath, newFilePath))
                openDoc.FileWatcher.RemoveFile(oldFilePath)
                openDoc.FileWatcher.StartWatchFile(openDoc)
        self.UpdateAllViews(hint = ("rename folder", self, oldFolderLogicPath, newFolderLogicPath))
        self.Modify(True)
        return True

    def GetSchemas(self):
        """Returns list of schema models (activegrid.model.schema.schema) for all schemas in this project."""
        
        rtn = []
        resourceFactory = self._GetResourceFactory()
        for projectFile in self.GetModel().projectFiles:
            if (projectFile.type == basedocmgr.FILE_TYPE_SCHEMA):
                schema = resourceFactory.getModel(projectFile)
                if (schema != None):
                    rtn.append(schema)

        return rtn
        
    def GetFiles(self):
        return self.GetModel().filePaths

    def GetStartupFile(self):
        return self.GetModel().StartupFile

    def GetFileRefs(self):
        return self.GetModel().findAllRefs()


    def SetFileRefs(self, fileRefs):
        return self.GetModel().setRefs(fileRefs)    


    def IsFileInProject(self, filename):
        return self.GetModel().FindFile(filename)
        

    def GetAppInfo(self):
        return self.GetModel().GetAppInfo()


    def GetAppDocMgr(self):
        return self.GetModel()
        

    def GetProjectName(self):
        return os.path.splitext(os.path.basename(self.GetFilename()))[0]


    def GetDeploymentFilepath(self, pre17=False):
        if (pre17):
            name = self.GetProjectName() + PRE_17_TMP_DPL_NAME
        else:
            name = self.GetProjectName() + _17_TMP_DPL_NAME
        return os.path.join(self.GetModel().homeDir, name)
    

    def _GetResourceFactory(self, preview=False, deployFilepath=None):
        return IDEResourceFactory(
            openDocs=wx.GetApp().GetDocumentManager().GetDocuments(),
            dataSourceService=wx.GetApp().GetService(DataModelEditor.DataSourceService),
            projectDir=os.path.dirname(self.GetFilename()),
            preview=preview,
            deployFilepath=deployFilepath)

    def GenerateDeployment(self, deployFilepath=None, preview=False):
        
        if ACTIVEGRID_BASE_IDE:
            return

        if not deployFilepath:
            deployFilepath = self.GetDeploymentFilepath()

        d = DeploymentGeneration.DeploymentGenerator(
            self.GetModel(), self._GetResourceFactory(preview,
                                                      deployFilepath))
                
        dpl = d.getDeployment(deployFilepath)

        if preview:
            dpl.initialize()  # used in preview only

        # REVIEW 07-Apr-06 stoens@activegrid.com -- Check if there's a
        # tmp dpl file with pre 17 name, if so, delete it, so user doesn't end
        # up with unused file in project dir. We should probably remove this
        # check after 1.7 goes out.
        fileutils.remove(self.GetDeploymentFilepath(pre17=True))

        deploymentlib.saveThroughCache(dpl.fileName, dpl)
        return deployFilepath
        

    def GetCommandProcessor(self):
        """
        Returns the command processor associated with this document.
        """
        return self._commandProcessor


    def SetCommandProcessor(self, processor):
        """
        Sets the command processor to be used for this document. The document
        will then be responsible for its deletion. Normally you should not
        call this; override OnCreateCommandProcessor instead.
        """
        self._commandProcessor = processor
        

class ProjectNameLocationPage(Wizard.BitmapTitledWizardPage):
    def __init__(self,master,add_bottom_page=True):
        Wizard.BitmapTitledWizardPage.__init__(self,master,_("Enter the name and location for the project"),_("Name and Location"),"python_logo.png")
        self.can_finish = True
        self.allowOverwriteOnPrompt = False
        sizer_frame = ttk.Frame(self)
        sizer_frame.grid(column=0, row=1, sticky="nsew")
        separator = ttk.Separator(sizer_frame, orient = tk.HORIZONTAL)
        separator.pack(side=tk.LEFT,fill="x",expand=1)
        
        sizer_frame = ttk.Frame(self)
        sizer_frame.grid(column=0, row=2, sticky="nsew")
        info_label = ttk.Label(sizer_frame, text=_("Enter the name and location for the project."))
        info_label.pack(side=tk.LEFT,fill="x",pady=(consts.DEFAUT_CONTRL_PAD_Y, consts.DEFAUT_CONTRL_PAD_Y))

        self.CreateTopPage()
        
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        if add_bottom_page:
            self.CreateBottomPage()
            
    def CreateTopPage(self):
        
        sizer_frame = ttk.Frame(self)
        sizer_frame.grid(column=0, row=3, sticky="nsew")
        self.name_label = ttk.Label(sizer_frame, text=_("Name:"))
        self.name_label.grid(column=0, row=0, sticky="nsew")
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(sizer_frame, textvariable=self.name_var)
        self.name_entry.grid(column=1, row=0, sticky="nsew",padx=(consts.DEFAUT_CONTRL_PAD_X/2,0))
        sizer_frame.columnconfigure(1, weight=1)
        
        self.dir_label = ttk.Label(sizer_frame, text=_("Location:"))
        self.dir_label.grid(column=0, row=1, sticky="nsew",pady=(consts.DEFAUT_CONTRL_PAD_Y, 0))
        self.dir_entry_var = tk.StringVar()
        self.dir_entry = ttk.Combobox(sizer_frame, textvariable=self.dir_entry_var)
        self.dir_entry.grid(column=1, row=1, sticky="nsew",padx=(consts.DEFAUT_CONTRL_PAD_X/2,0),pady=(consts.DEFAUT_CONTRL_PAD_Y, 0))
        self.browser_button = ttk.Button(
            sizer_frame, text=_("Browse..."), command=self.BrowsePath
        )
        self.browser_button.grid(column=2, row=1, sticky="nsew",padx=(consts.DEFAUT_CONTRL_PAD_X,0),pady=(consts.DEFAUT_CONTRL_PAD_Y, 0))
        
        self.rowconfigure(3, weight=1)
        return sizer_frame
        
    def CreateBottomPage(self,chk_box_row=4):
        
        sizer_frame = ttk.Frame(self)
        sizer_frame.grid(column=0, row=chk_box_row, sticky="nsew")
        self.project_dir_chkvar = tk.IntVar()
        self.create_project_dir_checkbutton = ttk.Checkbutton(
            sizer_frame, text=_("Create Project Name Directory"), variable=self.project_dir_chkvar
        )
        self.create_project_dir_checkbutton.pack(side=tk.LEFT,fill="x")

        sizer_frame = ttk.Frame(self)
        sizer_frame.grid(column=0, row=chk_box_row+1, sticky="nsew")

        self.infotext_label_var = tk.StringVar()
        self.infotext_label_var.set("")
        self.infotext_label = ttk.Label(
            sizer_frame, textvariable=self.infotext_label_var, foreground="red"
        )
        self.infotext_label.pack(side=tk.LEFT,fill="x",padx=(consts.DEFAUT_CONTRL_PAD_X,0))

        self.rowconfigure(chk_box_row, weight=1)
        self.rowconfigure(chk_box_row+1, weight=1)
        
    def BrowsePath(self):
        path = filedialog.askdirectory()
        if path:
            #必须转换一下路径为系统标准路径格式
            path = fileutils.opj(path)
            self.dir_entry_var.set(path)
        
    def Validate(self):
        self.infotext_label_var.set("")
        projName = self.name_var.get().strip()
        if projName == "":
            self.infotext_label_var.set(_("Please provide a file name."))
            return False
        #项目名称不能包含空格
        if projName.find(' ') != -1:
            self.infotext_label_var.set(_("Please provide a file name that does not contains spaces."))        
            return False

        if projName[0].isdigit():
            self.infotext_label_var.set(_("File name cannot start with a number.  Please enter a different name."))            
            return False
        if projName.endswith(consts.PROJECT_EXTENSION):
            projName2 = projName[:-4]
        else:
            projName2 = projName
        #项目名称必须是字母或数字,下划线字符串允许合法
        if not projName2.replace("_", "a").isalnum():  # [a-zA-Z0-9_]  note '_' is allowed and ending '.agp'.
            self.infotext_label_var.set(_("Name must be alphanumeric ('_' allowed).  Please enter a valid name."))
            return False

        dirName = self.dir_entry_var.get().strip()
        if dirName == "":
            self.infotext_label_var.set(_("No directory.  Please provide a directory."))            
            return False
        if os.sep == "\\" and dirName.find("/") != -1:
            self.infotext_label_var.set(_("Wrong delimiter '/' found in directory path.  Use '%s' as delimiter.") % os.sep)            
            return False
        
        return True
        
    def GetProjectLocation(self):
        projName = self.name_var.get().strip()
        dirName = self.dir_entry_var.get()
        #是否创建项目名称目录,如果是则目录包含项目名称
        if self.project_dir_chkvar.get():
            dirName = os.path.join(dirName,projName)
        return dirName
        
    def Finish(self):
        dirName = self.GetProjectLocation()
        #if dir not exist,create it first
        if not os.path.exists(dirName):
            parserutils.MakeDirs(dirName)
            
        projName = self.name_var.get().strip()
        fullProjectPath = os.path.join(dirName, strutils.MakeNameEndInExtension(projName, consts.PROJECT_EXTENSION))
        if os.path.exists(fullProjectPath):
            if self.allowOverwriteOnPrompt:
                res = wx.MessageBox(_("That %sfile already exists. Would you like to overwrite it.") % infoString, "File Exists", style=wx.YES_NO|wx.NO_DEFAULT)
                if res != wx.YES:
                    return False
            else:                
                messagebox.showinfo(_("File Exists"),_("That file already exists. Please choose a different name."))
                return False
                
            # What if the document is already open and we're overwriting it?
            documents = docManager.GetDocuments()
            for document in documents:
                if os.path.normcase(document.GetFilename()) == os.path.normcase(self._fullProjectPath):  # If the renamed document is open, update it
                    document.DeleteAllViews()
                    break
            os.remove(self._fullProjectPath)
   
        self._project_configuration = self.GetPojectConfiguration()
        utils.profile_set(PROJECT_DIRECTORY_KEY, self._project_configuration.Location)
        docManager = GetApp().GetDocumentManager()
        template = docManager.FindTemplateForTestPath(consts.PROJECT_EXTENSION)
        doc = template.CreateDocument(fullProjectPath, flags = core.DOC_NEW)
        #set project name
        doc.GetModel().Name = self._project_configuration.Name
        doc.GetModel().Id = str(uuid.uuid1()).upper()
        doc.GetModel().SetInterpreter(self._project_configuration.Interpreter)
        doc.OnSaveDocument(fullProjectPath)
        view = GetApp().MainFrame.GetProjectView().GetView()
        view.AddProjectToView(doc)
        return True
        
    def GetPojectConfiguration(self):
        return baserun.BaseProjectConfiguration(self.name_var.get(),self.dir_entry_var.get(),self.project_dir_chkvar.get())
        
class NewProjectWizard(Wizard.BaseWizard):
    def __init__(self, parent):
        self._parent = parent
        Wizard.BaseWizard.__init__(self, parent)
        self._project_template_page = self.CreateProjectTemplatePage(self)
        self.template_pages = {
        }
        self.project_template_icon = GetApp().GetImage("packagefolder_obj.gif")
        self.project_templates = ProjectTemplateManager().ProjectTemplates
        self.LoadProjectTemplates()
        
    def CreateProjectTemplatePage(self,wizard):
        page = Wizard.BitmapTitledWizardPage(wizard, _("New Project Wizard"),_("Welcom to new project wizard"),"python_logo.png")    
       # self.vert_scrollbar = SafeScrollbar(self, orient=tk.VERTICAL)
        #self.vert_scrollbar.grid(row=0, column=1, sticky=tk.NSEW)

        # init and place tree
        
        sizer_frame = ttk.Frame(page)
        sizer_frame.grid(column=0, row=1, sticky="nsew")
        #设置path列存储模板路径,并隐藏改列 
        self.tree = ttk.Treeview(sizer_frame)
        self.tree.pack(side=tk.LEFT,fill="both",expand=1)
      #  self.vert_scrollbar["command"] = self.tree.yview
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        # init tree events
        self.tree.bind("<<TreeviewSelect>>", self._on_select, True)
        #鼠标双击Tree控件事件
        self.tree.bind("<Double-Button-1>", self.on_double_click, "+")

        # configure the only tree column
        self.tree.column("#0", anchor=tk.W, stretch=True)
        self.tree["show"] = ("tree",)

        wizard.FitToPage(page)
        return page

    def LoadDefaultProjectTemplates(self):
        ProjectTemplateManager().AddProjectTemplate(_("Gernal"),_("Empty Project"),[ProjectNameLocationPage,])
        ProjectTemplateManager().AddProjectTemplate(_("Gernal"),_("New Project From Existing Code"),["noval.project.baseviewer.ProjectNameLocationPage",])

    def LoadProjectTemplates(self):
        self.LoadDefaultProjectTemplates()
        for template_catlog in self.project_templates:
            catlogs = template_catlog.split('/')
            path = ''
            for i,catlog_name in enumerate(catlogs):
                if i == 0:
                    path += catlog_name
                else:
                    path += "/" + catlog_name
                #found表示是否已经存在改路径的节点,node_id,表示从该节点下面插入
                found,node_id = self.GetProjectTemplateNode(path)
                if not found:
                    node_id = self.tree.insert(node_id, "end", text=catlog_name,image=self.project_template_icon,values=path)
                    self.tree.selection_set(node_id)
            for template_name,pages in self.project_templates[template_catlog]:
                #treeview不能存储包含空格的路径,故需要先把空格去掉
                template_path = template_catlog + "/" + template_name
                template_node_id = self.tree.insert(node_id, "end", text=template_name,values=(template_path,))
                page_instances = self.InitPageInstances(pages)
                self.SetPagesChain(page_instances)
                self.template_pages[template_path] = page_instances
                
    def InitPageInstances(self,pages):
        page_instances = []
        for page_info in pages:
            args = {}
            #如果页面初始化需要参数,则使用列表或元祖的方式指定页面和参数信息
            if isinstance(page_info,list) or isinstance(page_info,tuple):
                #列表的第一个元素为页面名称或类名
                page_class = page_info[0]
                #列表第二个元素为页面启动的参数,为字典类型
                args = page_info[1]
            else:
                page_class = page_info
            if isinstance(page_class,str):
                page_class_parts = page_class.split(".")
                page_module_name = ".".join(page_class_parts[0:-1])
                page_class_name = page_class_parts[-1]
                #如果模块名称包含多级层,必须设置fromlist参数为True
                page_module = __import__(page_module_name,fromlist=True)
                page_class = getattr(page_module,page_class_name)
            try:
                page = page_class(self,**args)
            except Exception as e:
                utils.get_logger().error("init page instance error %s",e)
            page_instances.append(page)
        return page_instances

    def SetPagesChain(self,pages):
        '''
            设置各页面的链接关系
        '''
        if len(pages) == 0:
            return
        for i,page in enumerate(pages):
            if i >= len(pages) - 1:
                continue
            pages[i+1].SetPrev(pages[i])
            pages[i].SetNext(pages[i+1])

    def GetProjectTemplatePathNode(self, folderPath,item=None):
        for child in self.tree.get_children(item):
            #获取存储的路径值
            path = self.tree.set(child, "path")
            if folderPath == path:
                return child
            else:
                node_id = self.GetProjectTemplatePathNode(folderPath,child)
                if node_id:
                    return node_id
        return ''

    def GetProjectTemplateNode(self, path):
        found = self.GetProjectTemplatePathNode(path)
        sub_path = '/'.join(path.split('/')[0:-1])
        parent_node = self.GetProjectTemplatePathNode(sub_path)
        return found,parent_node
        
    def _on_select(self,event):
        
        def update_ui(enable=False):
            if enable:
                self.next_button['state'] = tk.NORMAL
            else:
                self.next_button['state'] = tk.DISABLED
            self.prev_button['state'] = tk.DISABLED
            self.SetFinish(False)
        nodes = self.tree.selection()
        if len(nodes) == 0:
            update_ui(False)
            return
        node = nodes[0]
        path = self.tree.item(node)["values"][0]
        childs = self.tree.get_children(node)
        if len(childs) > 0:
            update_ui(False)
        else:
            pages = self.template_pages[path]
            #单独设置起始页的下一个页面为第一个页面
            pages[0].SetPrev(self._project_template_page)
            self._project_template_page.SetNext(pages[0])
            update_ui(True)
            
    def on_double_click(self,event):
        nodes = self.tree.selection()
        node = nodes[0]
        childs = self.tree.get_children(node)
        if len(childs) == 0:
            self.GotoNextPage()
        
class ProjectTemplate(core.DocTemplate):

    def CreateDocument(self, path, flags,wizard_cls=NewProjectWizard):
        if path:
            doc = core.DocTemplate.CreateDocument(self, path, flags)
            if path:
                doc.GetModel()._projectDir = os.path.dirname(path)
            return doc
        else:
            wiz = wizard_cls(GetApp())
            wiz.RunWizard(wiz._project_template_page)
            return None  # never return the doc, otherwise docview will think it is a new file and rename it


class ProjectView(misc.AlarmEventView):
    COPY_FILE_TYPE = 1
    CUT_FILE_TYPE = 2
    #----------------------------------------------------------------------------
    # Overridden methods
    #----------------------------------------------------------------------------

    def __init__(self, frame):
        misc.AlarmEventView.__init__(self)
        self._prject_browser = frame  # not used, but kept to match other Services
        self._treeCtrl = self._prject_browser.tree
        self._loading = False  # flag to not to try to saving state of folders while it is loading
        self._documents = []
        self._document = None
        self._bold_item = None

    def GetDocumentManager(self):  # Overshadow this since the superclass uses the view._viewDocument attribute directly, which the project editor doesn't use since it hosts multiple docs
        return GetApp().GetDocumentManager()

    def Destroy(self):
        projectService = wx.GetApp().GetService(ProjectService)
        if projectService:
            projectService.SetView(None)
        wx.lib.docview.View.Destroy(self)
        
    @property
    def IsImportStop(self):
        return self._prject_browser.stop_import

    @property
    def Documents(self):
        return self._documents
        
    def GetDocument(self):
        return self._document

    def GetFrame(self):
        return self._prject_browser

    def SetDocument(self,document):
        self._document = document
        
    def Activate(self, activate = True):
        if self.IsShown():
            core.View.Activate(self, activate = activate)
            if activate and self._treeCtrl:
                self._treeCtrl.focus_set()
        self.Show()

    def OnCreate(self, doc, flags):
        return True

    def OnChangeFilename(self):
        pass

    def ProjectSelect(self):
        selItem = self._prject_browser.project_combox.current()
        if selItem == -1:
            self._prject_browser.project_combox.set("")
            return
        document = self._documents[selItem]
        self.SetDocument(document)
        self.LoadProject(self.GetDocument())
        if self.GetDocument():
            filename = self.GetDocument().GetFilename()
        else:
            filename = ''
       # self._projectChoice.SetToolTipString(filename)


    def OnSize(self, event):
        event.Skip()
        wx.CallAfter(self.GetFrame().Layout)


    def OnBeginDrag(self, event):
        if self.GetMode() == ProjectView.RESOURCE_VIEW:
            return
            
        item = event.GetItem()
        if item.IsOk():
            self._draggingItems = []
            for item in self._treeCtrl.GetSelections():
                if self._IsItemFile(item):
                    self._draggingItems.append(item)
            if len(self._draggingItems):
                event.Allow()


    def OnEndDrag(self, event):
        item = event.GetItem()
        if item.IsOk():
            files = []
            for ditem in self._draggingItems:
                file = self._GetItemFile(ditem)
                if file not in files:
                    files.append(file)
                    
            folderPath = self._GetItemFolderPath(item)

            self.GetDocument().GetCommandProcessor().Submit(ProjectMoveFilesCommand(self.GetDocument(), files, folderPath))


    def WriteProjectConfig(self):
        config = GetApp().GetConfig()
        if config.ReadInt(consts.PROJECT_DOCS_SAVED_KEY, True):
            projectFileNames = []
            curProject = None
            for i in range(len(self._prject_browser.project_combox['values'])):
                project_document = self._documents[i]
                if not project_document.OnSaveModified():
                    return
                if project_document.GetDocumentSaved():  # Might be a new document and "No" selected to save it
                    projectFileNames.append(str(project_document.GetFilename()))
            config.Write(consts.PROJECT_SAVE_DOCS_KEY, projectFileNames.__repr__())

            document = None
            if self._prject_browser.project_combox['values']:
                i = self._prject_browser.project_combox.current()
                if i != -1:
                    document = self._documents[i]
            if document:
                config.Write(consts.CURRENT_PROJECT_KEY, document.GetFilename())
            else:
                config.DeleteEntry(consts.CURRENT_PROJECT_KEY)


    def OnClose(self, deleteWindow = True):
        self.WriteProjectConfig()
            
        project = self.GetDocument()
        if not project:
            return True
        if not project.Close():
            return True

        if not deleteWindow:
            self.RemoveCurrentDocumentUpdate()
        else:
            # need this to accelerate closing down app if treeCtrl has lots of items
            rootItem = self._treeCtrl.GetRootItem()
            self._treeCtrl.DeleteChildren(rootItem)
        

        # We don't need to delete the window since it is a floater/embedded
        return True


    def _GetParentFrame(self):
        return wx.GetTopLevelParent(self.GetFrame())
        
    def AddProgressFiles(self,newFilePaths,range_value,projectDoc,progress_ui):
        global DEFAULT_PROMPT_MESSAGE_ID

      ###  self._treeCtrl.UnselectAll()
        project = projectDoc.GetModel()
        projectDir = project.homeDir
        rootItem = self._treeCtrl.GetRootItem()
        # add new folders and new items
        addList = []                    
        for filePath in newFilePaths:
            file = project.FindFile(filePath)
            if file:
                folderPath = file.logicalFolder
                if folderPath:
                    if os.path.basename(filePath).lower() == self.PACKAGE_INIT_FILE:
                        self._treeCtrl.AddPackageFolder(folderPath)
                    else:
                        self._treeCtrl.AddFolder(folderPath)
                    folder = self._treeCtrl.FindFolder(folderPath)
                else:
                    folder = rootItem
                if folderPath is None:
                    folderPath = ""
                dest_path = os.path.join(projectDir,folderPath,os.path.basename(filePath))
                if not parserutils.ComparePath(filePath,dest_path):
                    if os.path.exists(dest_path):
                        project.RemoveFile(file)
                        #选择yes和no将显示覆盖确认对话框
                        if DEFAULT_PROMPT_MESSAGE_ID == constants.ID_YES or DEFAULT_PROMPT_MESSAGE_ID == constants.ID_NO:
                            prompt_dlg = ui_common.PromptmessageBox(parent,_("Project File Exists"),\
                                    _("The file %s is already exist in project ,Do You Want to overwrite it?") % filePath)
                            ui_common.show_dialog(prompt_dlg)
                            DEFAULT_PROMPT_MESSAGE_ID = prompt_dlg.status
                            #选择No时不要覆盖文件
                            if DEFAULT_PROMPT_MESSAGE_ID == wx.ID_NO:
                                range_value += 1
                     #           Publisher.sendMessage(ImportFiles.NOVAL_MSG_UI_IMPORT_FILES_PROGRESS,value=range_value,\
                      #                          is_cancel=self._stop_importing)
                                continue
                    dest_dir_path = os.path.dirname(dest_path)
                    if not os.path.exists(dest_dir_path):
                        parserutils.MakeDirs(dest_dir_path)
                        
                    #选择yestoall和notoall将不再显示覆盖确认对话框
                    if DEFAULT_PROMPT_MESSAGE_ID == constants.ID_YESTOALL or \
                                DEFAULT_PROMPT_MESSAGE_ID == constants.ID_YES:
                        shutil.copyfile(filePath,dest_path)
                    file.filePath = dest_path
                if not self._treeCtrl.FindItem(file.filePath,folder):
                    item = self._treeCtrl.AppendItem(folder, os.path.basename(file.filePath), file)
                    addList.append(item)
                self._treeCtrl.item(folder, open=True)
            range_value += 1
          ###  progress_ui.SetProgress(range_value,self.IsImportStop)
            print (range_value,"================")
            assert(type(range_value) == int and range_value > 0)
            if self.IsImportStop:
                utils.get_logger().info("user stop import code")
                break
        # sort folders with new items
        parentList = []
        for item in addList:
            parentItem = self._treeCtrl.parent(item)
            if parentItem not in parentList:
                parentList.append(parentItem)
        for parentItem in parentList:
            self._treeCtrl.SortChildren(parentItem)
            self._treeCtrl.item(parentItem, open=True)

    def OnUpdate(self, sender = None, hint = None):
        if core.View.OnUpdate(self, sender, hint):
            return
        
        if hint:
            if hint[0] == consts.PROJECT_ADD_COMMAND_NAME:
                projectDoc = hint[1]
                if self.GetDocument() != projectDoc:  # project being updated isn't currently viewed project
                    return
                newFilePaths = hint[2]  # need to be added and selected, and sorted
                oldFilePaths = hint[3]  # need to be selected
                
                project = projectDoc.GetModel()
                projectDir = project.homeDir
                rootItem = self._treeCtrl.GetRootItem()
                    
                # add new folders and new items
                addList = []                    
                for filePath in newFilePaths:
                    file = project.FindFile(filePath)
                    if file:
                        folderPath = file.logicalFolder
                        if folderPath:
                            if os.path.basename(filePath).lower() == self.PACKAGE_INIT_FILE:
                                self._treeCtrl.AddFolder(folderPath,True)
                            else:
                                self._treeCtrl.AddFolder(folderPath)
                            folder = self._treeCtrl.FindFolder(folderPath)
                        else:
                            folder = rootItem
                        if folderPath is None:
                            folderPath = ""
                        dest_path = os.path.join(projectDir,folderPath,os.path.basename(filePath))
                        if not parserutils.ComparePath(filePath,dest_path):
                            if os.path.exists(dest_path):
                                #the dest file is already in the project
                                if project.FindFile(dest_path):
                                    project.RemoveFile(file)
                                if DEFAULT_PROMPT_MESSAGE_ID == constants.ID_YES or \
                                            DEFAULT_PROMPT_MESSAGE_ID == constants.ID_NO:
                                    prompt_dlg = ProjectUI.PromptMessageDialog(wx.GetApp().GetTopWindow(),-1,_("Project File Exists"),\
                                            _("The file %s is already exist in project ,Do You Want to overwrite it?") % filePath)
                                    status = prompt_dlg.ShowModal()
                                    ProjectUI.PromptMessageDialog.DEFAULT_PROMPT_MESSAGE_ID = status
                                    prompt_dlg.Destroy()
                            if DEFAULT_PROMPT_MESSAGE_ID == constants.ID_YESTOALL or\
                                DEFAULT_PROMPT_MESSAGE_ID == constants.ID_YES:
                                try:
                                    shutil.copyfile(filePath,dest_path)
                                except Exception as e:
                                    messagebox.showerror(GetApp().GetAppName(),str(e))
                                    return
                            file.filePath = dest_path
                        if not self._treeCtrl.FindItem(file.filePath,folder):
                            #如果是虚拟文件,则返回为None
                            item = self._treeCtrl.AppendItem(folder, os.path.basename(file.filePath), file)
                            if item is not None:
                                addList.append(item)
                        self._treeCtrl.item(folder, open=True)
                # sort folders with new items
                parentList = []
                for item in addList:
                    parentItem = self._treeCtrl.parent(item)
                    if parentItem not in parentList:
                        parentList.append(parentItem)
                for parentItem in parentList:
                    self._treeCtrl.SortChildren(parentItem)

                # select all the items user wanted to add
                lastItem = None
                for filePath in (oldFilePaths + newFilePaths):
                    item = self._treeCtrl.FindItem(filePath)
                    if item:
                        self._treeCtrl.SelectItem(item)
                        lastItem = item
                        
                if lastItem:        
                    self._treeCtrl.see(lastItem)
                return
                
            elif hint[0] == consts.PROJECT_ADD_PROGRESS_COMMAND_NAME:
                projectDoc = hint[1]
                if self.GetDocument() != projectDoc:  # project being updated isn't currently viewed project
                    return
                newFilePaths = hint[2]  # need to be added and selected, and sorted
                range_value = hint[3]  # need to be selected
                progress_ui = hint[4]
                self.AddProgressFiles(newFilePaths,range_value,projectDoc,progress_ui)
                return

            elif hint[0] == "remove":
                projectDoc = hint[1]
                if self.GetDocument() != projectDoc:  # project being updated isn't currently viewed project
                    return
             
                filePaths = hint[2]
                for filePath in filePaths:
                    item = self._treeCtrl.FindItem(filePath)
                    if item:
                        self._treeCtrl.delete(item)
                return
                
            elif hint[0] == "rename":
                projectDoc = hint[1]
                if self.GetDocument() != projectDoc:  # project being updated isn't currently viewed project
                    return
                    
                self._treeCtrl.Freeze()
                try:
                    item = self._treeCtrl.FindItem(hint[2])
                    self._treeCtrl.SetItemText(item, os.path.basename(hint[3]))
                    self._treeCtrl.EnsureVisible(item)
                finally:
                    self._treeCtrl.Thaw()
                return
                
            elif hint[0] == "rename folder":
                projectDoc = hint[1]
                if self.GetDocument() != projectDoc:  # project being updated isn't currently viewed project
                    return
                    
                self._treeCtrl.Freeze()
                try:
                    item = self._treeCtrl.FindFolder(hint[2])
                    if item:
                        self._treeCtrl.UnselectAll()
                        self._treeCtrl.SetItemText(item, os.path.basename(hint[3]))
                        self._treeCtrl.SortChildren(self._treeCtrl.GetItemParent(item))
                        self._treeCtrl.SelectItem(item)
                        self._treeCtrl.EnsureVisible(item)
                finally:
                    self._treeCtrl.Thaw()
                return
     

    def RemoveProjectUpdate(self, projectDoc):
        """ Called by service after deleting a project, need to remove from project choices """
        i = self._projectChoice.FindString(self._MakeProjectName(projectDoc))
        self._projectChoice.Delete(i)

        numProj = self._projectChoice.GetCount()
        if i >= numProj:
            i = numProj - 1
        if i >= 0:
            self._projectChoice.SetSelection(i)
        self._documents.remove(self._document)
        wx.GetApp().GetDocumentManager().CloseDocument(projectDoc, False)
        self._document = None
        self.OnProjectSelect()
        
    def ReloadDocuments(self):
        names = []
        for document in self._documents:
            names.append(self._MakeProjectName(document))
        self._prject_browser.project_combox['values'] = names


    def RemoveCurrentDocumentUpdate(self, i=-1):
        """ Called by service after deleting a project, need to remove from project choices """
        i = self._prject_browser.project_combox.current()
        self._documents.remove(self._document)
        self.ReloadDocuments()
        numProj = len(self._documents)
        if i >= numProj:
            i = numProj - 1
        if i >= 0:
            self._prject_browser.project_combox.current(i)
        self._document = None
        self.ProjectSelect()
 
    def CloseProject(self):
        projectDoc = self.GetDocument()
        if projectDoc:
            openDocs = self.GetDocumentManager().GetDocuments()
            #close all open documents of this project first
            for openDoc in openDocs[:]:  # need to make a copy, as each file closes we're off by one
                if projectDoc == openDoc:  # close project last
                    continue
                    
                if projectDoc == self._prject_browser.FindProjectFromMapping(openDoc):
                    self.GetDocumentManager().CloseDocument(openDoc, False)
                    
                    self._prject_browser.RemoveProjectMapping(openDoc)
                    if hasattr(openDoc, "GetModel"):
                        self._prject_browser.RemoveProjectMapping(openDoc.GetModel())
            #delete project regkey config
           ## wx.ConfigBase_Get().DeleteGroup(getProjectKeyName(projectDoc.GetModel().Id))
            projectDoc.document_watcher.RemoveFileDoc(projectDoc)
            if self.GetDocumentManager().CloseDocument(projectDoc, False):
                self.RemoveCurrentDocumentUpdate()
            if not self.GetDocument():
                self.AddProjectRoot(_("Projects"))
            
    def OnResourceViewToolClicked(self, event):
        id = event.GetId()
        if id == ResourceView.REFRESH_PATH_ID or id == ResourceView.ADD_FOLDER_ID:
            return self.dir_ctrl.ProcessEvent(event)
            
    def SetProjectStartupFile(self):
        item = self._treeCtrl.GetSingleSelectItem()
        self.SetProjectStartupFileItem(item)
        
    def SetProjectStartupFileItem(self,item):
        if item == self._bold_item:
            return
        if self._bold_item is not None:
            self._treeCtrl.SetItemBold(self._bold_item ,False)
        filePath = self._GetItemFile(item)
        pjfile = self.GetDocument().GetModel().FindFile(filePath)
        self._treeCtrl.SetItemBold(item)
        self._bold_item = item
        self.GetDocument().GetModel().StartupFile = pjfile
        self.GetDocument().Modify(True)
        
    def NewProject(self,event):
        docManager = wx.GetApp().GetDocumentManager()
        for template in docManager.GetTemplates():
            if template.GetDocumentType() == ProjectDocument:
                doc = template.CreateDocument("", flags = wx.lib.docview.DOC_NEW)
                break
                
    def OpenProject(self,event):
        descr = _("Project File") + "(*%s)|*%s" % (PROJECT_EXTENSION,PROJECT_EXTENSION)
        dlg = wx.FileDialog(self.GetFrame(),_("Open Project") ,
                       wildcard = descr,
                       style=wx.OPEN|wx.FILE_MUST_EXIST|wx.CHANGE_DIR)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        project_path = dlg.GetPath()
        dlg.Destroy()
        
        doc = self.GetDocumentManager().CreateDocument(project_path, wx.lib.docview.DOC_SILENT|wx.lib.docview.DOC_OPEN_ONCE)
        if not doc:  # project already open
            self.SetProject(project_path)
        elif doc:
            AddProjectMapping(doc)
                
    def SaveProject(self):
        doc = self.GetDocument()
        if doc.IsModified():
            GetApp().configure(cursor="circle")
            GetApp().GetTopWindow().PushStatusText(_("Project is saving..."))
            if doc.OnSaveDocument(doc.GetFilename()):
                GetApp().GetTopWindow().PushStatusText(_("Project save success."))
            else:
                GetApp().GetTopWindow().PushStatusText(_("Project save failed."))
            GetApp().configure(cursor="")
            
    def CleanProject(self):
        project_doc = self.GetDocument()
        path = os.path.dirname(project_doc.GetFilename())
        #
        GetApp().configure(cursor="circle")
        for root,path,files in os.walk(path):
            for filename in files:
                fullpath = os.path.join(root,filename)
                ext = strutils.get_file_extension(fullpath)
                #清理项目的二进制文件
                if ext in project_doc.BIN_FILE_EXTS:
                    GetApp().GetTopWindow().PushStatusText(_("Cleaning \"%s\".") % fullpath)
                    try:
                        os.remove(fullpath)
                    except:
                        pass
        GetApp().GetTopWindow().PushStatusText(_("Clean Completed."))
        GetApp().configure(cursor="")
        
    def ArchiveProject(self):
        GetApp().configure(cursor="circle")
        doc = self.GetDocument()
        path = os.path.dirname(doc.GetFilename())
        try:
            GetApp().GetTopWindow().PushStatusText(_("Archiving..."))
            datetime_str = datetime.datetime.strftime(datetime.datetime.now(), '%Y%m%d%H%M%S')
            zip_name = doc.GetModel().Name + "_" + datetime_str + ".zip"
            zip_path = doc.ArchiveProject(os.path.join(path,zip_name))
            messagebox.showinfo(_("Archive Success"),_("Success archived to %s") % zip_path)
            GetApp().GetTopWindow().PushStatusText(_("Success archived to %s") % zip_path)
        except Exception as e:
            msg = unicode(e)
            utils.get_logger().exception("")
            messagebox.showerror(_("Archive Error"),msg)
            GetApp().GetTopWindow().PushStatusText(_("Archive Error"))
        GetApp().configure(cursor="")
                
    def OpenProjectPath(self,event):
        document = self.GetDocument()
        fileutils.open_file_directory(document.GetFilename())
        
    def OpenFolderPath(self,event):
        document = self.GetDocument()
        project_path = os.path.dirname(document.GetFilename())
        item = self._treeCtrl.GetSingleSelectItem()
        if self._IsItemFile(item):
            filePath = self._GetItemFilePath(item)
        else:
            filePath = fileutils.opj(os.path.join(project_path,self._GetItemFolderPath(item)))
        err_code,msg = fileutils.open_file_directory(filePath)
        if err_code != ERROR_OK:
            wx.MessageBox(msg,style = wx.OK|wx.ICON_ERROR)
        
    def OpenPromptPath(self,event):
        document = self.GetDocument()
        project_path = os.path.dirname(document.GetFilename())
        item = self._treeCtrl.GetSingleSelectItem()
        if self._IsItemFile(item):
            filePath = os.path.dirname(self._GetItemFilePath(item))
        else:
            filePath = fileutils.opj(os.path.join(project_path,self._GetItemFolderPath(item)))
        err_code,msg = fileutils.open_path_in_terminator(filePath)
        if err_code != ERROR_OK:
            wx.MessageBox(msg,style = wx.OK|wx.ICON_ERROR)
            
    def CopyPath(self,event):
        document = self.GetDocument()
        project_path = os.path.dirname(document.GetFilename())
        item = self._treeCtrl.GetSingleSelectItem()
        if self._IsItemFile(item):
            filePath = self._GetItemFilePath(item)
        else:
            filePath = fileutils.opj(os.path.join(project_path,self._GetItemFolderPath(item)))
        sysutilslib.CopyToClipboard(filePath)

    def ImportFilesToProject(self,event):
        items = self._treeCtrl.GetSelections()
        if items:
            item = items[0]
        else:
            item = self._treeCtrl.GetRootItem()
        folderPath = self._GetItemFolderPath(item)
        frame = ImportFiles.ImportFilesDialog(wx.GetApp().GetTopWindow(),-1,_("Import Files"),folderPath)
        frame.CenterOnParent()
        if frame.ShowModal() == wx.ID_OK:
            if not self._treeCtrl.IsExpanded(item):
                self._treeCtrl.Expand(item)
            #muse unsubscribe the registered msg,otherwise will sendmessage to the deleted dialog
            Publisher.unsubscribe(frame.UpdateImportProgress,ImportFiles.NOVAL_MSG_UI_IMPORT_FILES_PROGRESS)
        frame.Destroy()

    #----------------------------------------------------------------------------
    # Display Methods
    #----------------------------------------------------------------------------

    def IsShown(self):
        return GetApp().MainFrame.IsViewShown(consts.PROJECT_VIEW_NAME)


    def Hide(self):
        self.Show(False)


    def Show(self, show = True):
        pass
        #GetApp().MainFrame.ShowView(consts.PROJECT_VIEW_NAME)
       # if wx.GetApp().IsMDI():
        #    mdiParentFrame = wx.GetApp().GetTopWindow()
        #    mdiParentFrame.ShowEmbeddedWindow(self.GetFrame(), show)


    #----------------------------------------------------------------------------
    # Methods for ProjectDocument and ProjectService to call
    #----------------------------------------------------------------------------

    def SetProject(self, projectPath):
        if self._prject_browser.IsLoading:
            utils.get_logger().info("app is loading projects at startup ,do not load project document %s at this time",projectPath)
            return
            
        #打开项目文件时强制显示项目视图窗口,不生成事件
        GetApp().MainFrame.GetProjectView(show=True,generate_event=False)
        curSel = self._prject_browser.project_combox.current()
        for i in range(len(self._prject_browser.project_combox['values'])):
            document = self._documents[i]
            if document.GetFilename() == projectPath:
                if curSel != i:  # don't reload if already loaded
                    utils.get_logger().info("switch to and load project document %s",projectPath)
                    self._prject_browser.project_combox.current(i)
                    self.SetDocument(document)
                    self.LoadProject(document)
                    #self._projectChoice.SetToolTipString(document.GetFilename())
                break

    def GetSelectedFile(self):
        for item in self._treeCtrl.selection():
            filePath = self._GetItemFilePath(item)
            if filePath:
                return filePath
        return None


    def GetSelectedFiles(self):
        filePaths = []
        for item in self._treeCtrl.GetSelections():
            filePath = self._GetItemFilePath(item)
            if filePath and filePath not in filePaths:
                filePaths.append(filePath)
        return filePaths


    def GetSelectedPhysicalFolder(self):
        if self.GetMode() == ProjectView.PROJECT_VIEW:
            return None
        else:
            for item in self._treeCtrl.GetSelections():
                if not self._IsItemFile(item):
                    filePath = self._GetItemFolderPath(item)
                    if filePath:
                        return filePath
            return None


    def GetSelectedProject(self):
        document = self.GetDocument()
        if document:
            return document.GetFilename()
        else:
            return None
            
    def GetProjectSelection(self,document):
        for i in range(len(self._prject_browser.project_combox['values'])):
            project = self._documents[i]
            if document == project:
                return i
        return -1

    def AddProjectToView(self, document):
        #check the project is already exist or not
        index = self.GetProjectSelection(document)
        #if proejct not exist,add the new document
        if index == -1:
            index = self._prject_browser.AddProject(self._MakeProjectName(document))
            self._documents.append(document)
        self._prject_browser.project_combox.current(index)
        self.ProjectSelect()
        
    def LoadDocuments(self):
        self._projectChoice.Clear()
        for document in self._documents:
            i = self._projectChoice.Append(self._MakeProjectName(document),getProjectBitmap(), document)
            if document == self.GetDocument():
                self._projectChoice.SetSelection(i)
                
    def AddProjectRoot(self,document_or_name):
        self._prject_browser.clear()
        if utils.is_py3_plus():
            basestring_ = str
        elif utils.is_py2():
            basestring_ = basestring
        if isinstance(document_or_name,basestring_):
            name = document_or_name
            text = name
        else:
            document = document_or_name
            text = document.GetModel().Name
        root_item = self._treeCtrl.insert("", "end", text=text,image=self._treeCtrl.GetProjectIcon())
        return root_item
        
    def AddFolderItem(self,document,folderPath):
        return self._treeCtrl.AddFolder(folderPath)

    def LoadProject(self, document):
      #  wx.GetApp().GetTopWindow().SetCursor(wx.StockCursor(wx.CURSOR_WAIT))
        try:
            rootItem = self.AddProjectRoot(document)
            if document:
                docFilePath = document.GetFilename()
                folders = document.GetModel().logicalFolders
                folders.sort()
                folderItems = []
                for folderPath in folders:
                    folderItems = folderItems + self.AddFolderItem(document,folderPath)
                                            
                for file in document.GetModel()._files:
                    folder = file.logicalFolder
                    if folder:
                        folderTree = folder.split('/')
                        item = rootItem
                        for folderName in folderTree:
                            found = False
                            for child in self._treeCtrl.get_children(item):
                                if self._treeCtrl.item(child, "text") == folderName:
                                    item = child 
                                    found = True
                                    break
                                
                            if not found:
                                #print "error folder '%s' not found for %s" % (folder, file.filePath)
                                break
                    else:
                        item = rootItem
                        
                    fileItem = self._treeCtrl.AppendItem(item, os.path.basename(file.filePath), file)
                    if file.IsStartup:
                        self._bold_item = fileItem
                        self._treeCtrl.SetItemBold(fileItem)
                        document.GetModel().StartupFile = file
                    
                self._treeCtrl.SortChildren(rootItem)
                for item in folderItems:
                    self._treeCtrl.SortChildren(item)
                    
                if utils.profile_get_int("LoadFolderState", True):
                    self.LoadFolderState()
    
                self._treeCtrl.focus_set()
                child = self._treeCtrl.GetFirstChild(self._treeCtrl.GetRootItem())
                if child:
                    self._treeCtrl.see(child)
    
                
             #   if self._embeddedWindow:
              #      document.GetCommandProcessor().SetEditMenu(wx.GetApp().GetEditMenu(self._GetParentFrame()))

        finally:
            pass
            #self._treeCtrl.Thaw()
            #wx.GetApp().GetTopWindow().SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))


    def ProjectHasFocus(self):
        """ Does Project Choice have focus """
        return (wx.Window.FindFocus() == self._projectChoice)


    def FilesHasFocus(self):
        """ Does Project Tree have focus """
        winWithFocus = wx.Window.FindFocus()
        if not winWithFocus:
            return False
        while winWithFocus:
            if winWithFocus == self._treeCtrl:
                return True
            winWithFocus = winWithFocus.GetParent()
        return False


    def ClearFolderState(self):
        config = wx.ConfigBase_Get()
        config.DeleteGroup(getProjectKeyName(self.GetDocument().GetModel().Id))
        

    def SaveFolderState(self, event=None):
        """ 保存项目文件夹打开或关闭状态 """

        if self._loading:
            return
            
        folderList = []
        folderItemList = self._GetFolderItems(self._treeCtrl.GetRootItem())
        for item in folderItemList:
            #判断节点是否处于展开状态,如果是,则保存展开状态
            if self._treeCtrl.item(item, "open"):
                folderList.append(self._GetItemFolderPath(item))
        utils.profile_set(getProjectKeyName(self.GetDocument().GetModel().Id), repr(folderList))


    def LoadFolderState(self):
        """ 加载项目文件夹打开或关闭状态"""
        self._loading = True
      
        config = GetApp().GetConfig()
        openFolderData = config.Read(getProjectKeyName(self.GetDocument().GetModel().Id), "")
        if openFolderData:
            folderList = eval(openFolderData)
            folderItemList = self._GetFolderItems(self._treeCtrl.GetRootItem())
            for item in folderItemList:
                folderPath = self._GetItemFolderPath(item)
                if folderPath in folderList:
                    #展开节点
                    self._treeCtrl.item(item, open=True)
                else:
                    #关闭节点
                    self._treeCtrl.item(item, open=False)
        self._loading = False


    #----------------------------------------------------------------------------
    # Control events
    #----------------------------------------------------------------------------

    def OnProperties(self, event):
        if self.ProjectHasFocus():
            self.OnProjectProperties()
        elif self.FilesHasFocus():
            items = self._treeCtrl.GetSelections()
            if not items:
                return
            item = items[0]
            filePropertiesService = wx.GetApp().GetService(Property.FilePropertiesService)
            filePropertiesService.ShowPropertiesDialog(self.GetDocument(),item)

    def OnProjectProperties(self, option_name=None):
        if self.GetDocument():
            filePropertiesService = wx.GetApp().GetService(Property.FilePropertiesService)
            filePropertiesService.ShowPropertiesDialog(self.GetDocument(),self._treeCtrl.GetRootItem(),option_name)
            
    def OnAddNewFile(self,event):
        items = self._treeCtrl.GetSelections()
        if items:
            item = items[0]
            folderPath = self._GetItemFolderPath(item)
        else:
            folderPath = ""
        frame = NewFile.NewFileDialog(self.GetFrame(),-1,_("New FileType"),folderPath)
        frame.CenterOnParent()
        if frame.ShowModal() == wx.ID_OK:
            if self.GetDocument().GetCommandProcessor().Submit(ProjectAddFilesCommand(self.GetDocument(), [frame.file_path], folderPath=folderPath)):
                self.OnOpenSelection(None)
        frame.Destroy()

    def OnAddFolder(self, event):
        if self.GetDocument():
            items = self._treeCtrl.GetSelections()
            if items:
                item = items[0]
                if self._IsItemFile(item):
                    item = self._treeCtrl.GetItemParent(item)
                    
                folderDir = self._GetItemFolderPath(item)
            else:
                folderDir = ""
                
            if folderDir:
                folderDir += "/"
            folderPath = "%sUntitled" % folderDir
            i = 1
            while self._treeCtrl.FindFolder(folderPath):
                i += 1
                folderPath = "%sUntitled%s" % (folderDir, i)
            projectdir = self.GetDocument().GetModel().homeDir
            destfolderPath = os.path.join(projectdir,folderPath)
            try:
                os.mkdir(destfolderPath)
            except Exception as e:
                wx.MessageBox(str(e),style=wx.OK|wx.ICON_ERROR)
                return
            self.GetDocument().GetCommandProcessor().Submit(ProjectAddFolderCommand(self, self.GetDocument(), folderPath))
            #空文件夹下创建一个虚拟文件,防止空文件夹节点被删除
            dummy_file = os.path.join(destfolderPath,DUMMY_NODE_TEXT)
            self.GetDocument().GetCommandProcessor().Submit(ProjectAddFilesCommand(self.GetDocument(),[dummy_file],folderPath))
            self._treeCtrl.UnselectAll()
            item = self._treeCtrl.FindFolder(folderPath)
            self._treeCtrl.SelectItem(item)
            self._treeCtrl.EnsureVisible(item)
            self.OnRename()

    def AddFolder(self, folderPath):
        self._treeCtrl.AddFolder(folderPath)
        return True

    def DeleteFolder(self, folderPath,delete_folder_files=True):
        if delete_folder_files:
            projectdir = self.GetDocument().GetModel().homeDir
            folder_local_path = os.path.join(projectdir,folderPath)
            if os.path.exists(folder_local_path):
                try:
                    fileutils.RemoveDir(folder_local_path)
                except Exception as e:
                    messagebox.showerror( _("Delete Folder"),"Could not delete '%s'.  %s" % (os.path.basename(folder_local_path), e),
                                              parent= self.GetFrame())
                    return
        item = self._treeCtrl.FindFolder(folderPath)
        self.DeleteFolderItems(item)
        self._treeCtrl.delete(item)
        return True
        
    def DeleteFolderItems(self,folder_item):
        files = []
        items = self._treeCtrl.get_children(folder_item)
        for item in items:
            if self._treeCtrl.GetChildrenCount(item):
                self.DeleteFolderItems(item)
            else:
                file = self._GetItemFile(item)
                files.append(file)
        if files:
            self.GetDocument().GetCommandProcessor().Submit(projectcommand.ProjectRemoveFilesCommand(self.GetDocument(), files))

    def OnAddFileToProject(self):
        project_template = self.GetDocumentManager().FindTemplateForTestPath(consts.PROJECT_EXTENSION)
        descrs = strutils.gen_file_filters(project_template.GetDocumentType())
        paths = filedialog.askopenfilename(
                master=self._prject_browser,
                filetypes=descrs,
                initialdir=os.getcwd(),
                multiple=True
        )
        if not paths:
            return

        folderPath = None
        item = self._treeCtrl.GetSingleSelectItem()
        if item:
            if not self._IsItemFile(item):
                folderPath = self._GetItemFolderPath(item)
        self.GetDocument().GetCommandProcessor().Submit(projectcommand.ProjectAddFilesCommand(self.GetDocument(), paths, folderPath=folderPath))
        self.Activate()  # after add, should put focus on project editor


    def OnAddDirToProject(self):
        frame = wx.Dialog(wx.GetApp().GetTopWindow(), -1, _("Add Directory Files to Project"), size= (320,200))
        contentSizer = wx.BoxSizer(wx.VERTICAL)

        flexGridSizer = wx.FlexGridSizer(cols = 2, vgap=HALF_SPACE, hgap=HALF_SPACE)
        flexGridSizer.Add(wx.StaticText(frame, -1, _("Directory:")), 0, wx.ALIGN_CENTER_VERTICAL, 0)
        lineSizer = wx.BoxSizer(wx.HORIZONTAL)
        dirCtrl = wx.TextCtrl(frame, -1, os.path.dirname(self.GetDocument().GetFilename()), size=(250,-1))
        dirCtrl.SetToolTipString(dirCtrl.GetValue())
        lineSizer.Add(dirCtrl, 1, wx.ALIGN_CENTER_VERTICAL|wx.EXPAND)
        findDirButton = wx.Button(frame, -1, _("Browse..."))
        lineSizer.Add(findDirButton, 0, wx.LEFT|wx.ALIGN_CENTER_VERTICAL, HALF_SPACE)
        flexGridSizer.Add(lineSizer, 1, wx.EXPAND)

        def OnBrowseButton(event):
            dlg = wx.DirDialog(frame, _("Choose a directory:"), style=wx.DD_DEFAULT_STYLE)
            dir = dirCtrl.GetValue()
            if len(dir):
                dlg.SetPath(dir)
            dlg.CenterOnParent()
            if dlg.ShowModal() == wx.ID_OK:
                dirCtrl.SetValue(dlg.GetPath())
                dirCtrl.SetToolTipString(dirCtrl.GetValue())
                dirCtrl.SetInsertionPointEnd()
            dlg.Destroy()
        wx.EVT_BUTTON(findDirButton, -1, OnBrowseButton)

        visibleTemplates = []
        for template in self.GetDocumentManager()._templates:
            if template.IsVisible():
                visibleTemplates.append(template)

        choices = []
        descr = ''
        for template in visibleTemplates:
            if len(descr) > 0:
                descr = descr + _('|')
            descr = _(template.GetDescription()) + " (" + template.GetFileFilter() + ")"
            choices.append(descr)
        choices.insert(0, _("All Files") + "(*.*)")  # first item
        filterChoice = wx.Choice(frame, -1, size=(250, -1), choices=choices)
        filterChoice.SetSelection(0)
        filterChoice.SetToolTipString(_("Select file type filter."))
        flexGridSizer.Add(wx.StaticText(frame, -1, _("Files of type:")), 0, wx.ALIGN_CENTER_VERTICAL)
        flexGridSizer.Add(filterChoice, 1, wx.EXPAND)

        contentSizer.Add(flexGridSizer, 0, wx.ALL|wx.EXPAND, SPACE)

        subfolderCtrl = wx.CheckBox(frame, -1, _("Add files from subdirectories"))
        subfolderCtrl.SetValue(True)
        contentSizer.Add(subfolderCtrl, 0, wx.LEFT|wx.ALIGN_CENTER_VERTICAL, SPACE)

        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        findBtn = wx.Button(frame, wx.ID_OK, _("Add"))
        findBtn.SetDefault()
        buttonSizer.Add(findBtn, 0, wx.RIGHT, HALF_SPACE)
        buttonSizer.Add(wx.Button(frame, wx.ID_CANCEL), 0)
        contentSizer.Add(buttonSizer, 0, wx.ALL|wx.ALIGN_RIGHT, SPACE)

        frame.SetSizer(contentSizer)
        frame.Fit()

        frame.CenterOnParent()
        status = frame.ShowModal()

        passedCheck = False
        while status == wx.ID_OK and not passedCheck:
            if not os.path.exists(dirCtrl.GetValue()):
                dlg = wx.MessageDialog(frame,
                                       _("'%s' does not exist.") % dirCtrl.GetValue(),
                                       _("Find in Directory"),
                                       wx.OK | wx.ICON_EXCLAMATION
                                       )
                dlg.CenterOnParent()
                dlg.ShowModal()
                dlg.Destroy()

                status = frame.ShowModal()
            else:
                passedCheck = True

        frame.Destroy()

        if status == wx.ID_OK:
            wx.GetApp().GetTopWindow().SetCursor(wx.StockCursor(wx.CURSOR_WAIT))

            try:
                doc = self.GetDocument()
                searchSubfolders = subfolderCtrl.IsChecked()
                dirString = dirCtrl.GetValue()
    
                if os.path.isfile(dirString):
                    # If they pick a file explicitly, we won't prevent them from adding it even if it doesn't match the filter.
                    # We'll assume they know what they're doing.
                    paths = [dirString]
                else:
                    paths = []
    
                    index = filterChoice.GetSelection()
                    lastIndex = filterChoice.GetCount()-1
                    if index and index != lastIndex:  # if not All or Any
                        template = visibleTemplates[index-1]
    
                    # do search in files on disk
                    for root, dirs, files in os.walk(dirString):
                        if not searchSubfolders and root != dirString:
                            break
    
                        for name in files:
                            if index == 0:  # All
                                filename = os.path.join(root, name)
                                # if already in project, don't add it, otherwise undo will remove it from project even though it was already in it.
                                if not doc.IsFileInProject(filename):
                                    paths.append(filename)
                            else:  # use selected filter
                                if template.FileMatchesTemplate(name):
                                    filename = os.path.join(root, name)
                                    # if already in project, don't add it, otherwise undo will remove it from project even though it was already in it.
                                    if not doc.IsFileInProject(filename):
                                        paths.append(filename)
    
                folderPath = None
                if self.GetMode() == ProjectView.PROJECT_VIEW:
                    selections = self._treeCtrl.GetSelections()
                    if selections:
                        item = selections[0]
                        if not self._IsItemFile(item):
                            folderPath = self._GetItemFolderPath(item)

                doc.GetCommandProcessor().Submit(ProjectAddFilesCommand(doc, paths, folderPath=folderPath))
                self.Activate()  # after add, should put focus on project editor
                
            finally:
                wx.GetApp().GetTopWindow().SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))


    def DoAddFilesToProject(self, filePaths, folderPath):
        # method used by Drag-n-Drop to add files to current Project
        self.GetDocument().GetCommandProcessor().Submit(ProjectAddFilesCommand(self.GetDocument(), filePaths, folderPath))


    def OnFocus(self, event):
        self.GetDocumentManager().ActivateView(self)
        event.Skip()


    def OnKillFocus(self, event):
        # Get the top MDI window and "activate" it since it is already active from the perspective of the MDIParentFrame
        # wxBug: Would be preferable to call OnActivate, but have casting problem, so added Activate method to docview.DocMDIChildFrame
        if not self._editingSoDontKillFocus:  # wxBug: This didn't used to happen, but now when you start to edit an item in a wxTreeCtrl it puts out a KILL_FOCUS event, so we need to detect it
            topWindow = wx.GetApp().GetTopWindow()
            # wxBug: On Mac, this event can fire during shutdown, even after GetTopWindow()
            # is set to NULL. So make sure we have a TLW before getting the active child.
            if topWindow:
                childFrame = topWindow.GetActiveChild()
                if childFrame:
                    childFrame.Activate()
        event.Skip()

    def OnRename(self, event=None):
        items = self._treeCtrl.selection()
        if not items:
            return
        item = items[0]
        if utils.is_linux():
            dlg = wx.TextEntryDialog(self.GetFrame(), _("Enter New Name"), _("Enter New Name"))
            dlg.CenterOnParent()
            if dlg.ShowModal() == wx.ID_OK:
                text = dlg.GetValue()
                self.ChangeLabel(item, text)
        else:
            if items:
                self._treeCtrl.EditLabel(item)

    def OnEndLabelEdit(self, item,newName):
        if item == self._treeCtrl.GetRootItem():
            if not newName:
                #wx.MessageBox(_("project name could not be empty"),style=wx.OK|wx.ICON_ERROR)
                return
            else:
                #检查项目名称是否改变
                if self.GetDocument().GetModel().Name != newName:
                    self.GetDocument().GetModel().Name = newName
                    self.GetDocument().Modify(True)
                    #修改节点文本
                    self._treeCtrl.item(item,text=newName)
            return
        
        if not self.ChangeLabel(item, newName):
            return
            

    def ChangeLabel(self, item, newName):
        if not newName:
            return False
        if self._IsItemFile(item):
            oldFilePath = self._GetItemFilePath(item)
            newFilePath = os.path.join(os.path.dirname(oldFilePath), newName)
            doc = self.GetDocument()
            parent_item = self._treeCtrl.parent(item)
            if not doc.GetCommandProcessor().Submit(projectcommand.ProjectRenameFileCommand(doc, oldFilePath, newFilePath)):
                return False
            self._treeCtrl.SortChildren(self._treeCtrl.parent(parent_item))
        else:
            oldFolderPath = self._GetItemFolderPath(item)
            newFolderPath = os.path.dirname(oldFolderPath)
            if newFolderPath:
                newFolderPath += "/"
            newFolderPath += newName
            if newFolderPath == oldFolderPath:
                return True
            if self._treeCtrl.FindFolder(newFolderPath):
                messagebox.showwarning(_("Rename Folder"),_("Folder '%s' already exists.") % newName,parent=self.GetFrame())
                return False
            doc = self.GetDocument()
            if not doc.GetCommandProcessor().Submit(projectcommand.ProjectRenameFolderCommand(doc, oldFolderPath, newFolderPath)):
                return False
            self._treeCtrl.SortChildren(self._treeCtrl.parent(item))
            #should delete the folder item ,other it will have double folder item
            self._treeCtrl.Delete(item)

        return True
        

    def CanPaste(self):
        # wxBug: Should be able to use IsSupported/IsSupportedFormat here
        #fileDataObject = wx.FileDataObject()
        #hasFilesInClipboard = wx.TheClipboard.IsSupportedFormat(wx.FileDataObject)
        hasFilesInClipboard = False
        if not wx.TheClipboard.IsOpened():
            if wx.TheClipboard.Open():
                fileDataObject = wx.CustomDataObject(DF_COPY_FILENAME)
                hasFilesInClipboard = wx.TheClipboard.GetData(fileDataObject)
                wx.TheClipboard.Close()
        return hasFilesInClipboard
        
    def CopyFileItem(self,actionType):
        
        fileDataObject = wx.CustomDataObject(DF_COPY_FILENAME)
        items = self._treeCtrl.GetSelections()
        file_items = []
        for item in items:
            filePath = self._GetItemFilePath(item)
            if filePath:
                d = {
                    'filePath':filePath,
                    'actionType':actionType
                }
                file_items.append(d)
        share_data = cPickle.dumps(file_items)
        fileDataObject.SetData(share_data)
        if fileDataObject.GetSize() > 0 and wx.TheClipboard.Open():
            wx.TheClipboard.SetData(fileDataObject)
            wx.TheClipboard.Close()


    def OnCut(self):
        self.CopyFileItem(self.CUT_FILE_TYPE)
        self.RemoveFromProject(event)

    def OnCopy(self):
        self.CopyFileItem(self.COPY_FILE_TYPE)
        
    def CopyToDest(self,src_path,file_name,dest_path,action_type):
        dest_file_path = os.path.join(dest_path,file_name)
        if not os.path.exists(dest_file_path):
            if action_type == self.COPY_FILE_TYPE:
                shutil.copy(src_path,dest_file_path)
            elif action_type == self.CUT_FILE_TYPE:
                shutil.move(src_path,dest_file_path)
            return dest_file_path
        src_dir_path = os.path.dirname(src_path)
        if not parserutils.ComparePath(src_dir_path,dest_path):
            if action_type == self.COPY_FILE_TYPE:
                ret = wx.MessageBox(_("Dest file is already exist,Do you want to overwrite it?"),_("Copy File"),\
                              wx.YES_NO|wx.ICON_QUESTION,self._GetParentFrame())
                if ret == wx.YES:
                    shutil.copy(src_path,dest_file_path)
            elif action_type == self.CUT_FILE_TYPE:
                ret = wx.MessageBox(_("Dest file is already exist,Do you want to overwrite it?"),_("Move File"),\
                              wx.YES_NO|wx.ICON_QUESTION,self._GetParentFrame())
                if ret == wx.YES:
                    shutil.move(src_path,dest_file_path)
            return dest_file_path
        if action_type == self.CUT_FILE_TYPE:
            return dest_file_path
        file_ext = strutils.GetFileExt(file_name)
        filename_without_ext = strutils.GetFilenameWithoutExt(file_name)
        if sysutilslib.isWindows():
            dest_file_name = _("%s - Copy.%s") % (filename_without_ext,file_ext)
            dest_file_path = os.path.join(dest_path,dest_file_name)
            if os.path.exists(dest_file_path):
                i = 2
                while os.path.exists(dest_file_path):
                    dest_file_name = _("%s - Copy (%d).%s") % (filename_without_ext,i,file_ext)
                    dest_file_path = os.path.join(dest_path,dest_file_name)
                    i += 1
        else:
            dest_file_name = _("%s (copy).%s") % (filename_without_ext,file_ext)
            dest_file_path = os.path.join(dest_path,dest_file_name)
            if os.path.exists(dest_file_path):
                i = 2
                while os.path.exists(dest_file_path):
                    if i == 2:
                        dest_file_name = _("%s (another copy).%s") % (filename_without_ext,file_ext)
                    elif i == 3:
                        dest_file_name = _("%s (%drd copy).%s") % (filename_without_ext,i,file_ext)
                    else:
                        dest_file_name = _("%s (%dth copy).%s") % (filename_without_ext,i,file_ext)
                    dest_file_path = os.path.join(dest_path,dest_file_name)
                    i += 1
        shutil.copy(src_path,dest_file_path)
        return dest_file_path

    def OnPaste(self, event):
        if wx.TheClipboard.Open():
            fileDataObject = wx.CustomDataObject(DF_COPY_FILENAME)
            if wx.TheClipboard.GetData(fileDataObject):
                folderPath = None
                dest_files = []
                if self.GetMode() == ProjectView.PROJECT_VIEW:
                    items = self._treeCtrl.GetSelections()
                    if items:
                        item = items[0]
                        if item:
                            folderPath = self._GetItemFolderPath(item)
                destFolderPath = os.path.join(self.GetDocument().GetModel().homeDir,folderPath)
                for src_file in cPickle.loads(fileDataObject.GetData()):
                    filepath =  src_file['filePath']
                    actionType = src_file['actionType']
                    filename = os.path.basename(filepath)
                    if not os.path.exists(filepath):
                        wx.MessageBox(_("The item '%s' does not exist in the project directory.It may have been moved,renamed or deleted.") % filename,style=wx.OK|wx.ICON_ERROR)
                        return
                    try:
                        if actionType == self.COPY_FILE_TYPE:
                            dest_file_path = self.CopyToDest(filepath,filename,destFolderPath,self.COPY_FILE_TYPE)
                            dest_files.append(dest_file_path)
                        elif actionType == self.CUT_FILE_TYPE:
                            dest_file_path = self.CopyToDest(filepath,filename,destFolderPath,self.CUT_FILE_TYPE)
                            dest_files.append(dest_file_path)
                        else:
                            assert(False)
                    except Exception as e:
                        wx.MessageBox(str(e),style=wx.OK|wx.ICON_ERROR)
                        return
                self.GetDocument().GetCommandProcessor().Submit(ProjectAddFilesCommand(self.GetDocument(), dest_files, folderPath))
            wx.TheClipboard.Close()


    def RemoveFromProject(self):
        items = self._treeCtrl.selection()
        files = []
        for item in items:
            if not self._IsItemFile(item):
                folderPath = self._GetItemFolderPath(item)
                self.GetDocument().GetCommandProcessor().Submit(projectcommand.ProjectRemoveFolderCommand(self, self.GetDocument(), folderPath))
            else:
                file = self._GetItemFile(item)
                if file:
                    files.append(file)
        if files:
            self.GetDocument().GetCommandProcessor().Submit(projectcommand.ProjectRemoveFilesCommand(self.GetDocument(), files))
        
    def GetOpenDocument(self,filepath):
        openDocs = self.GetDocumentManager().GetDocuments()[:]  # need copy or docs shift when closed
        for d in openDocs:
            if parserutils.ComparePath(d.GetFilename(),filepath):
                return d
        return None

    def DeleteFromProject(self):
        is_file_selected = False
        is_folder_selected = False
        if self._HasFilesSelected():
            is_file_selected = True
        if self._HasFoldersSelected():
            is_folder_selected = True
        if is_file_selected and not is_folder_selected:
            yesNoMsg = messagebox.askyesno(_("Delete Files"),_("Delete cannot be reversed.\n\nRemove the selected files from the\nproject and file system permanently?"),
                         parent=self.GetFrame())
        elif is_folder_selected and not is_file_selected:
            yesNoMsg = messagebox.askyesno(_("Delete Folder"),_("Delete cannot be reversed.\n\nRemove the selected folder and its files from the\nproject and file system permanently?"),
                         parent=self.GetFrame())
        elif is_folder_selected and is_file_selected:
            yesNoMsg = messagebox.askyesno(_("Delete Folder And Files"),_("Delete cannot be reversed.\n\nRemove the selected folder and files from the\nproject and file system permanently?"),
             parent=self.GetFrame())
        if yesNoMsg == False:
            return
        items = self._treeCtrl.selection()
        delFiles = []
        for item in items:
            if self._IsItemFile(item):
                filePath = self._GetItemFilePath(item)
                if filePath and filePath not in delFiles:
                    # remove selected files from file system
                    if os.path.exists(filePath):
                        try:
                            #close the open document first if file opened
                            open_doc =  self.GetOpenDocument(filePath)
                            if open_doc:
                                open_doc.Modify(False)  # make sure it doesn't ask to save the file
                                self.GetDocumentManager().CloseDocument(open_doc, True)
                            os.remove(filePath)
                        except:
                            wx.MessageBox("Could not delete '%s'.  %s" % (os.path.basename(filePath), sys.exc_value),
                                          _("Delete File"),
                                          wx.OK | wx.ICON_ERROR,
                                          self.GetFrame())
                            return
                    # remove selected files from project
                    self.GetDocument().RemoveFiles([filePath])
                    delFiles.append(filePath)
            else:
                file_items = self._GetFolderFileItems(item)
                for fileItem in file_items:
                    filePath = self._GetItemFilePath(fileItem)
                    open_doc = self.GetOpenDocument(filePath)
                    if open_doc:
                        open_doc.Modify(False)  # make sure it doesn't ask to save the file
                        self.GetDocumentManager().CloseDocument(open_doc, True)
                folderPath = self._GetItemFolderPath(item)
                self.GetDocument().GetCommandProcessor().Submit(projectcommand.ProjectRemoveFolderCommand(self, self.GetDocument(), folderPath,True))
            
    def DeleteProject(self, noPrompt=False, closeFiles=True, delFiles=True):
        
        class DeleteProjectDialog(ui_base.CommonModaldialog):
        
            def __init__(self, parent, doc):
                ui_base.CommonModaldialog.__init__(self, parent)
                self.title(_("Delete Project"))
                ttk.Label(self.main_frame,text=_("Delete cannot be reversed.\nDeleted files are removed from the file system permanently.\n\nThe project file '%s' will be closed and deleted.") % os.path.basename(doc.GetFilename())).\
                    pack(padx=consts.DEFAUT_CONTRL_PAD_X,fill="x",pady=(consts.DEFAUT_CONTRL_PAD_Y))
                self._delFilesChkVar = tk.IntVar(value=True)
                delFilesCtrl = ttk.Checkbutton(self.main_frame,text=_("Delete all files in project"),variable=self._delFilesChkVar)
                delFilesCtrl.pack(padx=consts.DEFAUT_CONTRL_PAD_X,fill="x")
                misc.create_tooltip(delFilesCtrl,_("Deletes files from disk, whether open or closed"))
                
                self._closeDeletedChkVar = tk.IntVar(value=True)
                closeDeletedCtrl = ttk.Checkbutton(self.main_frame,text=_("Close open files belonging to project"),variable=self._closeDeletedChkVar)
                closeDeletedCtrl.pack(padx=consts.DEFAUT_CONTRL_PAD_X,fill="x")
                misc.create_tooltip(closeDeletedCtrl,_("Closes open editors for files belonging to project"))
                self.AddokcancelButton()

        doc = self.GetDocument()
        if not noPrompt:
            dlg = DeleteProjectDialog(self.GetFrame(), doc)
            status = dlg.ShowModal()
            delFiles = dlg._delFilesChkVar.get()
            closeFiles = dlg._closeDeletedChkVar.get()
            if status == constants.ID_CANCEL:
                return

        if closeFiles or delFiles:
            filesInProject = doc.GetFiles()
            # don't remove self prematurely
            filePath = doc.GetFilename()
            if filePath in filesInProject:
                filesInProject.remove(filePath)
            
            # don't close/delete files outside of project's directory
            homeDir = doc.GetModel().homeDir + os.sep
            for filePath in filesInProject[:]:
                fileDir = os.path.dirname(filePath) + os.sep
                if not fileDir.startswith(homeDir):  
                    filesInProject.remove(filePath)

        if closeFiles:
            # close any open views of documents in the project
            openDocs = self.GetDocumentManager().GetDocuments()[:]  # need copy or docs shift when closed
            for d in openDocs:
                if d.GetFilename() in filesInProject:
                    d.Modify(False)  # make sure it doesn't ask to save the file
                    if isinstance(d.GetDocumentTemplate(), ProjectTemplate):  # if project, remove from project list drop down
                        if self.GetDocumentManager().CloseDocument(d, True):
                            self.RemoveProjectUpdate(d)
                    else:  # regular file
                        self.GetDocumentManager().CloseDocument(d, True)
                
        # remove files in project from file system
        if delFiles:
            dirPaths = []
            for filePath in filesInProject:
                if os.path.isfile(filePath):
                    try:
                        dirPath = os.path.dirname(filePath)
                        if dirPath not in dirPaths:
                            dirPaths.append(dirPath)
                            
                        os.remove(filePath)
                    except:
                        wx.MessageBox("Could not delete file '%s'.\n%s" % (filePath, sys.exc_value),
                                      _("Delete Project"),
                                      wx.OK | wx.ICON_ERROR,
                                      self.GetFrame())
                                      
        filePath = doc.GetFilename()
        
        self.ClearFolderState()  # remove from registry folder settings
        #delete project regkey config
        wx.ConfigBase_Get().DeleteGroup(getProjectKeyName(doc.GetModel().Id))

        # close project
        if doc:            
            doc.Modify(False)  # make sure it doesn't ask to save the project
            if self.GetDocumentManager().CloseDocument(doc, True):
                self.RemoveCurrentDocumentUpdate()
            doc.document_watcher.RemoveFileDoc(doc)

        # remove project file
        if delFiles:
            dirPath = os.path.dirname(filePath)
            if dirPath not in dirPaths:
                dirPaths.append(dirPath)
        if os.path.isfile(filePath):
            try:
                os.remove(filePath)
            except:
                wx.MessageBox("Could not delete project file '%s'.\n%s" % (filePath, sys.exc_value),
                              _("Delete Prjoect"),
                              wx.OK | wx.ICON_EXCLAMATION,
                              self.GetFrame())
            
        # remove empty directories from file system
        if delFiles:
            dirPaths.sort()     # sorting puts parent directories ahead of child directories
            dirPaths.reverse()  # remove child directories first

            for dirPath in dirPaths:
                if os.path.isdir(dirPath):
                    files = os.listdir(dirPath)
                    if not files:
                        try:
                            os.rmdir(dirPath)
                        except:
                            wx.MessageBox("Could not delete empty directory '%s'.\n%s" % (dirPath, sys.exc_value),
                                          _("Delete Project"),
                                          wx.OK | wx.ICON_EXCLAMATION,
                                          self.GetFrame())
        

    def OnKeyPressed(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_DELETE:
            self.RemoveFromProject(event)
        else:
            event.Skip()


    def OnSelectAll(self, event):
        project = self.GetDocument()
        if project:
            self.DoSelectAll(self._treeCtrl.GetRootItem())


    def DoSelectAll(self, parentItem):
        (child, cookie) = self._treeCtrl.GetFirstChild(parentItem)
        while child.IsOk():
            if self._IsItemFile(child):
                self._treeCtrl.SelectItem(child)
            else:
                self.DoSelectAll(child)
            (child, cookie) = self._treeCtrl.GetNextChild(parentItem, cookie)


    def OnOpenSelectionSDI(self, event):
        # Do a call after so that the second mouseclick on a doubleclick doesn't reselect the project window
        wx.CallAfter(self.OnOpenSelection, None)

    def GetOpenDocumentTemplate(self,project_file):
        template = None
        document_template_name = utils.profile_get(self.GetDocument().GetFileKey(project_file,"Open"),"")
        filename = os.path.basename(project_file.filePath)
        if not document_template_name:
            document_template_name = utils.profile_get("Open/filenames/%s" % filename,"")
            if not document_template_name:
                document_template_name = utils.profile_get("Open/extensions/%s" % strutils.get_file_extension(filename),"")
        if document_template_name:
            template = wx.GetApp().GetDocumentManager().FindTemplateForDocumentType(document_template_name)
        return template
        
    def OnOpenSelectionWith(self, event):
        item_file = self._GetItemFile(self._treeCtrl.GetSingleSelectItem())
        selected_file_path = item_file.filePath
        dlg = ProjectUI.EditorSelectionDialog(wx.GetApp().GetTopWindow(),-1,_("Editor Selection"),item_file,self.GetDocument())
        dlg.CenterOnParent()
        if dlg.ShowModal() == wx.ID_OK:
            found_view = utils.GetOpenView(selected_file_path)
            if found_view:
                ret = wx.MessageBox(_("The document \"%s\" is already open,Do you want to close it?") %selected_file_path,style=wx.YES_NO|wx.ICON_QUESTION)
                if ret == wx.YES:
                    found_view.Close()
                    document = found_view.GetDocument()
                    if document in self.GetDocumentManager().GetDocuments():
                        document.Destroy()
                    frame = found_view.GetFrame()
                    if frame:
                        frame.Destroy()
                else:
                    return
            doc = self.GetDocumentManager().CreateTemplateDocument(dlg.selected_template,selected_file_path, wx.lib.docview.DOC_SILENT)
            if doc is not None and dlg._is_changed and utils.GetOpenView(selected_file_path):
                iconIndex = self._treeCtrl.GetTemplateIconIndex(dlg.selected_template)
                if dlg.OpenwithMode == dlg.OPEN_WITH_FILE_PATH:
                    utils.ProfileSet(self.GetDocument().GetFileKey(item_file,"Open"),\
                                     dlg.selected_template.GetDocumentName())
                    file_template = wx.GetApp().GetDocumentManager().FindTemplateForPath(selected_file_path)
                    if file_template != dlg.selected_template:
                        item = self._treeCtrl.GetSelections()[0]
                        if iconIndex != -1:
                            self._treeCtrl.SetItemImage(item, iconIndex, wx.TreeItemIcon_Normal)
                            self._treeCtrl.SetItemImage(item, iconIndex, wx.TreeItemIcon_Expanded)
                        
                elif dlg.OpenwithMode == dlg.OPEN_WITH_FILE_NAME:
                    filename = os.path.basename(selected_file_path)
                    utils.ProfileSet("Open/filenames/%s" % filename,dlg.selected_template.GetDocumentName())
                    if iconIndex != -1:
                        self.ChangeItemsImageWithFilename(self._treeCtrl.GetRootItem(),filename,iconIndex)
                elif dlg.OpenwithMode == dlg.OPEN_WITH_FILE_EXTENSION:
                    extension = strutils.GetFileExt(os.path.basename(selected_file_path))
                    utils.ProfileSet("Open/extensions/%s" % extension,dlg.selected_template.GetDocumentName())
                    if iconIndex != -1:
                        self.ChangeItemsImageWithExtension(self._treeCtrl.GetRootItem(),extension,iconIndex)
                else:
                    assert(False)
        dlg.Destroy()
        

    def ChangeItemsImageWithFilename(self,parent_item,filename,icon_index):
        if parent_item is None:
            return
        (item, cookie) = self._treeCtrl.GetFirstChild(parent_item)
        while item:
            if self._IsItemFile(item):
                file_name = self._treeCtrl.GetItemText(item)
                if file_name == filename:
                    self._treeCtrl.SetItemImage(item, icon_index, wx.TreeItemIcon_Normal)
                    self._treeCtrl.SetItemImage(item, icon_index, wx.TreeItemIcon_Expanded)
            self.ChangeItemsImageWithFilename(item,filename,icon_index)
            (item, cookie) = self._treeCtrl.GetNextChild(parent_item, cookie)
        
    def ChangeItemsImageWithExtension(self,parent_item,extension,icon_index):
        if parent_item is None:
            return
        (item, cookie) = self._treeCtrl.GetFirstChild(parent_item)
        while item:
            if self._IsItemFile(item):
                file_name = self._treeCtrl.GetItemText(item)
                if strutils.GetFileExt(file_name) == extension:
                    self._treeCtrl.SetItemImage(item, icon_index, wx.TreeItemIcon_Normal)
                    self._treeCtrl.SetItemImage(item, icon_index, wx.TreeItemIcon_Expanded)
            self.ChangeItemsImageWithExtension(item,extension,icon_index)
            (item, cookie) = self._treeCtrl.GetNextChild(parent_item, cookie)
        
    def OnOpenSelection(self, event):
        if self.GetMode() == ProjectView.RESOURCE_VIEW:
            item = event.GetItem()
            ResourceView.ResourceView(self).OpenSelection(item)
            event.Skip()
            return
        doc = None
        try:
            items = self._treeCtrl.GetSelections()[:]
            for item in items:
                filepath = self._GetItemFilePath(item)
                file_template = None
                if filepath:
                    if not os.path.exists(filepath):
                        msgTitle = wx.GetApp().GetAppName()
                        if not msgTitle:
                            msgTitle = _("File Not Found")
                        yesNoMsg = wx.MessageDialog(self.GetFrame(),
                                      _("The file '%s' was not found in '%s'.\n\nWould you like to browse for the file?") % (wx.lib.docview.FileNameFromPath(filepath), wx.lib.docview.PathOnly(filepath)),
                                      msgTitle,
                                      wx.YES_NO|wx.ICON_QUESTION
                                      )
                        yesNoMsg.CenterOnParent()
                        status = yesNoMsg.ShowModal()
                        yesNoMsg.Destroy()
                        if status == wx.ID_NO:
                            continue
                        findFileDlg = wx.FileDialog(self.GetFrame(),
                                                 _("Choose a file"),
                                                 defaultFile=wx.lib.docview.FileNameFromPath(filepath),
                                                 style=wx.OPEN|wx.FILE_MUST_EXIST|wx.CHANGE_DIR
                                                )
                        # findFileDlg.CenterOnParent()  # wxBug: caused crash with wx.FileDialog
                        if findFileDlg.ShowModal() == wx.ID_OK:
                            newpath = findFileDlg.GetPath()
                        else:
                            newpath = None
                        findFileDlg.Destroy()
                        if newpath:
                            # update Project Model with new location
                            self.GetDocument().UpdateFilePath(filepath, newpath)
                            filepath = newpath
                        else:
                            continue
                    else:        
                        project_file = self._treeCtrl.GetPyData(item)
                        file_template = self.GetOpenDocumentTemplate(project_file)
                    if file_template:
                        doc = self.GetDocumentManager().CreateTemplateDocument(file_template,filepath, wx.lib.docview.DOC_SILENT|wx.lib.docview.DOC_OPEN_ONCE)
                    else:
                        doc = self.GetDocumentManager().CreateDocument(filepath, wx.lib.docview.DOC_SILENT|wx.lib.docview.DOC_OPEN_ONCE)
                    if not doc and filepath.endswith(PROJECT_EXTENSION):  # project already open
                        self.SetProject(filepath)
                    elif doc:
                        AddProjectMapping(doc)
                        

        except IOError as e:
            msgTitle = wx.GetApp().GetAppName()
            if not msgTitle:
                msgTitle = _("File Error")
            wx.MessageBox("Could not open '%s'." % wx.lib.docview.FileNameFromPath(filepath),
                          msgTitle,
                          wx.OK | wx.ICON_EXCLAMATION,
                          self.GetFrame())
        if event is None:
            return
        event.Skip()

    #----------------------------------------------------------------------------
    # Convenience methods
    #----------------------------------------------------------------------------

    def _HasFiles(self):
        if not self._treeCtrl:
            return False
        return self._treeCtrl.GetCount() > 1    #  1 item = root item, don't count as having files


    def _HasFilesSelected(self):
        if not self._treeCtrl:
            return False
        items = self._treeCtrl.selection()
        if not items:
            return False
        for item in items:
            if self._IsItemFile(item):
                return True
        return False


    def _HasFoldersSelected(self):
        if not self._treeCtrl:
            return False
        items = self._treeCtrl.selection()
        if not items:
            return False
        for item in items:
            if not self._IsItemFile(item):
                return True
        return False


    def _MakeProjectName(self, project):
        return project.GetPrintableName()


    def _GetItemFilePath(self, item):
        filePath = self._GetItemFile(item)
        if filePath:
            return filePath
        else:
            return None


    def _GetItemFolderPath(self, item):
        rootItem = self._treeCtrl.GetRootItem()
        if item == rootItem:
            return ""
            
        if self._IsItemFile(item):
            item = self._treeCtrl.GetItemParent(item)
        
        folderPath = ""
        while item != rootItem:
            if folderPath:
                folderPath = self._treeCtrl.item(item,"text") + "/" + folderPath
            else:
                folderPath = self._treeCtrl.item(item,"text")
            #获取父节点
            item = self._treeCtrl.parent(item)
            
        return folderPath

            
    def _GetItemFile(self, item):
        return self._treeCtrl.GetPyData(item)


    def _IsItemFile(self, item):
        return self._GetItemFile(item) != None


    def _IsItemProcessModelFile(self, item):
        if ACTIVEGRID_BASE_IDE:
            return False

        if self._IsItemFile(item):
            filepath = self._GetItemFilePath(item)
            ext = None
            for template in self.GetDocumentManager().GetTemplates():
                if template.GetDocumentType() == ProcessModelEditor.ProcessModelDocument:
                    ext = template.GetDefaultExtension()
                    break;
            if not ext:
                return False

            if filepath.endswith(ext):
                return True

        return False

    def _GetFolderItems(self, parentItem):
        folderItems = []
        childrenItems = self._treeCtrl.get_children(parentItem)
        for childItem in childrenItems:
            if not self._IsItemFile(childItem):
                folderItems.append(childItem)
                folderItems += self._GetFolderItems(childItem)
        return folderItems
        
    def _GetFolderFileItems(self, parentItem):
        fileItems = []
        childrenItems = self._treeCtrl.get_children(parentItem)
        for childItem in childrenItems:
            if self._IsItemFile(childItem):
                fileItems.append(childItem)
            else:
                fileItems.extend(self._GetFolderFileItems(childItem))
        return fileItems
        
    def check_for_external_changes(self):
        if self._asking_about_external_change:
            return
        self._asking_about_external_change = True
        if self._alarm_event == filewatcher.FileEventHandler.FILE_MODIFY_EVENT:
            ret = messagebox.askyesno(_("Reload Project.."),_("Project File \"%s\" has already been modified outside,Do you want to reload It?") % self.GetDocument().GetFilename(),parent=self.GetFrame())
            if ret == True:
                document = self.GetDocument()
                document.OnOpenDocument(document.GetFilename())
                
        elif self._alarm_event == filewatcher.FileEventHandler.FILE_MOVED_EVENT or \
             self._alarm_event == filewatcher.FileEventHandler.FILE_DELETED_EVENT:
            ret = messagebox.askyesno(_("Project not exist.."),_("Project File \"%s\" has already been moved or deleted outside,Do you want to close this Project?") % self.GetDocument().GetFilename(),parent=self.GetFrame())
            document = self.GetDocument()
            if ret == True:
                self.CloseProject()
            else:
                document.Modify(True)
                
        self._asking_about_external_change = False
        misc.AlarmEventView.check_for_external_changes(self)
                
    def UpdateUI(self, command_id):
        if command_id in[constants.ID_CLOSE_PROJECT,constants.ID_SAVE_PROJECT ,constants.ID_DELETE_PROJECT,constants.ID_CLEAN_PROJECT,\
                         constants.ID_ARCHIVE_PROJECT,constants.ID_IMPORT_FILES,constants.ID_ADD_FILES_TO_PROJECT,constants.ID_ADD_DIR_FILES_TO_PROJECT,\
                         constants.ID_PROPERTIES,constants.ID_OPEN_FOLDER_PATH]:
            return self.GetDocument() is not None
        elif command_id == constants.ID_ADD_CURRENT_FILE_TO_PROJECT:
            return self.GetDocument() is not None and GetApp().MainFrame.GetNotebook().get_current_editor() is not None
        return False
        
    def OnAddCurrentFileToProject(self):
        doc = self.GetDocumentManager().GetCurrentDocument()
        filepath = doc.GetFilename()
        projectDoc = self.GetDocument()
        if projectDoc.IsFileInProject(filepath):
            messagebox.showwarning(GetApp().GetAppName(),_("Current document is already in the project"))
            return
        folderPath = None
        if self.GetView().GetMode() == ProjectView.PROJECT_VIEW:
            selections = self.GetView()._treeCtrl.GetSelections()
            if selections:
                item = selections[0]
                folderPath = self.GetView()._GetItemFolderPath(item)
        if projectDoc.GetCommandProcessor().Submit(ProjectAddFilesCommand(projectDoc, [filepath],folderPath=folderPath)):
            AddProjectMapping(doc, projectDoc)
            self.GetView().Activate()  # after add, should put focus on project editor
            if folderPath is None:
                folderPath = ""
            newFilePath = os.path.join(projectDoc.GetModel().homeDir,folderPath,os.path.basename(filepath))
            if not os.path.exists(newFilePath):
                return
            if not parserutils.ComparePath(newFilePath,filepath):
                openDoc = doc.GetOpenDocument(newFilePath)
                if openDoc:
                    wx.MessageBox(_("Project file is already opened"),style = wx.OK|wx.ICON_WARNING)
                    openDoc.GetFirstView().GetFrame().SetFocus()
                    return
                doc.FileWatcher.StopWatchFile(doc)
                doc.SetFilename(newFilePath)
                doc.FileWatcher.StartWatchFile(doc)
            doc.SetDocumentModificationDate()

class ProjectFileDropTarget(newTkDnD.FileDropTarget):

    def __init__(self, view):
        newTkDnD.FileDropTarget.__init__(self)
        self._view = view

    def OnDropFiles(self, x, y, filePaths):
        """ Do actual work of dropping files into project """
        if self._view.GetDocument():
            folderPath = None
            folderItem = self._view._treeCtrl.FindClosestFolder(x,y)
            if folderItem:
                folderPath = self._view._GetItemFolderPath(folderItem)
            self._view.DoAddFilesToProject(filePaths, folderPath)
            return True
        return False


    def OnDragOver(self, x, y, default):
        """ Feedback to show copy cursor if copy is allowed """
        if self._view.GetDocument():  # only allow drop if project exists
            return wx.DragCopy
        return wx.DragNone

class ProjectOptionsPanel(ui_utils.BaseConfigurationPanel):


    def __init__(self, master,**kwargs):
        ui_utils.BaseConfigurationPanel.__init__(self,master=master,**kwargs)
        self.projectsavedoc_chkvar = tk.IntVar(value=utils.profile_get_int("ProjectSaveDocs", True))
        projSaveDocsCheckBox = ttk.Checkbutton(self, text=_("Remember open projects"),variable=self.projectsavedoc_chkvar)
        projSaveDocsCheckBox.pack(padx=consts.DEFAUT_CONTRL_PAD_X,fill="x",pady=(consts.DEFAUT_CONTRL_PAD_Y,0))
        
        self.promptSavedoc_chkvar = tk.IntVar(value=utils.profile_get_int("PromptSaveProjectFile", True))
        promptSaveCheckBox = ttk.Checkbutton(self, text=_("Warn when run and save modify project files"),variable=self.promptSavedoc_chkvar)
        promptSaveCheckBox.pack(padx=consts.DEFAUT_CONTRL_PAD_X,fill="x")
        
        self.loadFolderState_chkvar = tk.IntVar(value=utils.profile_get_int("LoadFolderState", True))
        loadFolderStateCheckBox = ttk.Checkbutton(self, text=_("Load folder state when open project"),variable=self.loadFolderState_chkvar)
        loadFolderStateCheckBox.pack(padx=consts.DEFAUT_CONTRL_PAD_X,fill="x")
##        if not ACTIVEGRID_BASE_IDE:
##            self._projShowWelcomeCheckBox = wx.CheckBox(self, -1, _("Show Welcome Dialog"))
##            self._projShowWelcomeCheckBox.SetValue(config.ReadInt("RunWelcomeDialog2", True))
##            projectSizer.Add(self._projShowWelcomeCheckBox, 0, wx.ALL, HALF_SPACE)
##            
##            sizer = wx.BoxSizer(wx.HORIZONTAL)
##            sizer.Add(wx.StaticText(self, -1, _("Default language for projects:")), 0, wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, HALF_SPACE)
##            self._langCtrl = wx.Choice(self, -1, choices=projectmodel.LANGUAGE_LIST)            
##            self._langCtrl.SetStringSelection(config.Read(APP_LAST_LANGUAGE, projectmodel.LANGUAGE_DEFAULT))
##            self._langCtrl.SetToolTipString(_("Programming language to be used throughout the project."))
##            sizer.Add(self._langCtrl, 0, wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, MAC_RIGHT_BORDER)
##            projectSizer.Add(sizer, 0, wx.ALL, HALF_SPACE)

    def OnUseSashSelect(self, event):
        if not self._useSashMessageShown:
            msgTitle = wx.GetApp().GetAppName()
            if not msgTitle:
                msgTitle = _("Document Options")
            wx.MessageBox("Project window embedded mode changes will not appear until the application is restarted.",
                          msgTitle,
                          wx.OK | wx.ICON_INFORMATION,
                          self.GetParent())
            self._useSashMessageShown = True


    def OnOK(self, optionsDialog):
        config = wx.ConfigBase_Get()
        config.WriteInt("ProjectSaveDocs", self._projSaveDocsCheckBox.GetValue())
        config.WriteInt("PromptSaveProjectFile", self._promptSaveCheckBox.GetValue())
        config.WriteInt("LoadFolderState", self._loadFolderStateCheckBox.GetValue())
        if not ACTIVEGRID_BASE_IDE:
            config.WriteInt("RunWelcomeDialog2", self._projShowWelcomeCheckBox.GetValue())
            config.Write(APP_LAST_LANGUAGE, self._langCtrl.GetStringSelection())
        return True


    def GetIcon(self):
        return getProjectIcon()

