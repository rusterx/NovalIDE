# -*- coding: utf-8 -*-
#-------------------------------------------------------------------------------
# Name:        ide.py
# Purpose:
#
# Author:      wukan
#
# Created:     2019-01-08
# Copyright:   (c) wukan 2019
# Licence:     GPL-3.0
#-------------------------------------------------------------------------------
import tkinter as tk
from noval import core,imageutils,consts,_,Locale,menu
import noval.python.parser.utils as parserutils
from dummy.userdb import UserDataDb
from noval.util import utils
import noval.util.strutils as strutils
import noval.constants as constants
from pkg_resources import resource_filename
import sys
import noval.util.logger as logger
import os
import noval.frame as frame
from noval.editor import text as texteditor
from noval.editor import imageviewer as imageviewer
import noval.misc as misc
import tkinter.font as tk_font
from tkinter import ttk
from noval.syntax import synglob
from noval.util import record
import noval.menu as tkmenu
import noval.editor.code as codeeditor
from noval.python.interpreter import InterpreterManager
import noval.update as updateutils
import noval.syntax.lang as lang
import noval.preference as preference
from tkinter import messagebox
import subprocess
import noval.generalopt as generalopt
import noval.ui_common as ui_common
import noval.project.baseviewer as baseprojectviewer
import noval.docposition as docposition
#这些导入模块未被引用,用于py2exe打包模块进library.zip里面去
import noval.fileview as fileview
import noval.find.findresult as findresult
import noval.base_ui_themes as base_ui_themes
import noval.clean_ui_themes as base_ui_themes
import noval.paren_matcher as paren_matcher

#----------------------------------------------------------------------------
# Classes
#----------------------------------------------------------------------------
class IDEApplication(core.App):

    def __init__(self):
        
        #程序自定义事件字典集合
        #自定义事件是指事件名称不以<开头,以<开头的均为tk内部事件
        self._event_handlers = {}  # type: Dict[str, Set[Callable]]
        core.App.__init__(self)

    def OnInit(self):
        args = sys.argv
        #设置软件是否处于调式模式运行
        if strutils.isInArgs("debug", args):
            self.SetAppName(consts.DEBUG_APPLICATION_NAME)
            self.SetDebug(True)
            self.SetSingleInstance(False)
        else:
            self.SetAppName(consts.APPLICATION_NAME)
            self.SetDebug(False)
            self.SetSingleInstance(True)
            
        logger.initLogging(self.GetDebug())
        if not core.App.OnInit(self):
            return False

    #    self.ShowSplash(self.GetIDESplashBitmap())
        self._open_project_path = None
        self.frame = None           
        self._pluginmgr = None  
        self._init_theming()
        self._config = utils.Config(self.GetAppName())
        #设置窗体大小
        self.geometry(
            "{0}x{1}+{2}+{3}".format(
                max(utils.profile_get_int(consts.FRAME_WIDTH_KEY), 320),
                max(utils.profile_get_int(consts.FRAME_HEIGHT_KEY), 240),
                min(
                    max(utils.profile_get_int(consts.FRAME_LEFT_LOC_KEY), 0),
                    self.winfo_screenwidth() - 200,
                ),
                min(
                    max(utils.profile_get_int(consts.FRAME_TOP_LOC_KEY), 0),
                    self.winfo_screenheight() - 200,
                ),
            )
        )
        #最大化窗口
        if utils.profile_get_int(consts.FRAME_MAXIMIZED_KEY,True):
            self.MaxmizeWindow()


        ##locale must be set as app member property,otherwise it will only workable when app start up
        ##it will not workable after app start up,the translation also will not work
        ###lang_id = GeneralOption.GetLangId(config.Read("Language",sysutilslib.GetLangConfig()))
        #lang_id = 60
        lang_id = 0
        if Locale.IsAvailable(lang_id):
            self.locale = Locale(lang_id)
            self.locale.AddCatalogLookupPathPrefix(os.path.join(utils.get_app_path(),'locale'))
            ibRet = self.locale.AddCatalog(consts.APPLICATION_NAME.lower())
            ibRet = self.locale.AddCatalog("wxstd")
            self.locale.AddCatalog("wxstock")
        else:
            utils.get_logger().error("lang id %d is not available",lang_id)

        docManager = core.DocManager()
        self.SetDocumentManager(docManager)

        # Note:  These templates must be initialized in display order for the "Files of type" dropdown for the "File | Open..." dialog
        #这个是默认模板,所有未知扩展名的文件类型均使用这个模板
        defaultTemplate = core.DocTemplate(docManager,
                _("All Files"),
                "*.*",
                os.getcwd(),
                ".txt",
                "Text Document",
                _("Text Editor"),
                texteditor.TextDocument,
                texteditor.TextView,
                core.TEMPLATE_INVISIBLE,
                icon = imageutils.getBlankIcon())
        docManager.AssociateTemplate(defaultTemplate)

        imageTemplate = core.DocTemplate(docManager,
                _("Image File"),
                "*.bmp;*.ico;*.gif;*.jpg;*.jpeg;*.png",
                os.getcwd(),
                ".png",
                "Image Document",
                _("Image Viewer"),
                imageviewer.ImageDocument,
                imageviewer.ImageView,
                #could not be newable
                core.TEMPLATE_NO_CREATE,
                icon = imageutils.get_image_file_icon())
        docManager.AssociateTemplate(imageTemplate)
        #创建项目模板
        self.CreateProjectTemplate()
        #创建各种支持编程语言的模板
        self.CreateLexerTemplates()
        self.LoadLexerTemplates()
        self.SetDefaultIcon(imageutils.get_default_icon())
        self._InitFonts()
        
        #默认菜单id列表,这些菜单在没有任何可编辑文本窗口时菜单处于灰色状态
        self._default_command_ids = []
        self._InitMenu()
        #先创建主框架
        self._InitMainFrame()
        #再初始化程序菜单及其命令
        self._InitCommands()
        
        #打开从命令行传递的参数文件
        self.OpenCommandLineArgs()
        
        #加载上次程序退出时的活跃项目
        self.SetCurrentProject()
        ###self.ShowTipfOfDay()
        if utils.profile_get_int(consts.CHECK_UPDATE_ATSTARTUP_KEY, True):
            self.after(1000,self.CheckUpdate)
        
        #初始化拖拽对象以支持拖拽打开文件功能,由于在linux下面加载dll耗时较长
        #故使加载函数延迟执行
        self.after(500,self.InitTkDnd)
        self.bind("TextInsert", self.EventTextChange, True)
        self.bind("TextDelete", self.EventTextChange, True)
        self.bind("<FocusIn>", self._on_focus_in, True)
        
        preference.PreferenceManager().AddOptionsPanel(preference.ENVIRONMENT_OPTION_NAME,preference.GENERAL_ITEM_NAME,generalopt.GeneralOptionPanel)
        preference.PreferenceManager().AddOptionsPanel(preference.ENVIRONMENT_OPTION_NAME,preference.PROJECT_ITEM_NAME,baseprojectviewer.ProjectOptionsPanel)
        preference.PreferenceManager().AddOptionsPanel(preference.ENVIRONMENT_OPTION_NAME,preference.TEXT_ITEM_NAME,texteditor.TextOptionsPanel)
        return True
        
    def AppendDefaultCommand(self,command_id):
        self._default_command_ids.append(command_id)
        
    def InitTkDnd(self):
        core.App.InitTkDnd(self)
        if self.dnd is not None:
            self.event_generate("InitTkDnd")
        self.event_generate("<<AppInitialized>>")

    def _on_focus_in(self, event):
        openDocs = self.GetDocumentManager().GetDocuments()
        for doc in openDocs:
            if isinstance(doc,baseprojectviewer.ProjectDocument):
                view = self.MainFrame.GetProjectView(False).GetView()
            else:
                view = doc.GetFirstView()
            if hasattr(view,"_is_external_changed"):
                if view._is_external_changed:
                    view.check_for_external_changes()
        
    def EventTextChange(self,event):
        '''
            文本改变时重新对代码着色,同时更改代码大纲显示内容
        '''
        if hasattr(event, "text_widget"):
            text = event.text_widget
        else:
            text = event.widget
        if not hasattr(text, "syntax_colorer"):
            if isinstance(text, codeeditor.CodeCtrl):
                class_ = text.GetColorClass()
                text.syntax_colorer = class_(text)
        if isinstance(text, codeeditor.CodeCtrl):
            text.syntax_colorer.schedule_update(event, True)
            
        #只有文本编辑区域才在内容更改时更新大纲显示内容
        if isinstance(text.master.master,core.DocTabbedChildFrame):
            self.MainFrame.GetView(consts.OUTLINE_VIEW_NAME)._update_frame_contents()
        
    def CreateLexerTemplates(self):
        synglob.LexerFactory().CreateLexerTemplates(self.GetDocumentManager())
        
    def LoadLexerTemplates(self):
        synglob.LexerFactory().LoadLexerTemplates(self.GetDocumentManager())
        
    def CreateProjectTemplate(self):
        raise Exception("This method must be implemented in derived class")
        
    def GetDefaultLangId(self):
        return lang.ID_LANG_TXT

    def CheckUpdate(self,ignore_error=True):
        updateutils.CheckAppUpdate(ignore_error)
    
    @property
    def MainFrame(self):
        return self.frame
                
    def GotoView(self,file_path,lineNum=-1,colno=-1,trace_track=True):
        file_path = os.path.abspath(file_path)
        docs = self.GetDocumentManager().CreateDocument(file_path, core.DOC_SILENT|core.DOC_OPEN_ONCE)
        if docs == []:
            return
        foundView = docs[0].GetFirstView()
        if foundView:
            foundView.GetFrame().SetFocus()
            foundView.Activate()
            if not hasattr(foundView,"GotoLine"):
                return
            if colno == -1:
                foundView.GotoLine(lineNum)
            else:
                #定位到具体位置时是否追踪位置
                if trace_track:
                    foundView.GotoPos(lineNum,colno)
                else:
                    foundView.GetCtrl().GotoPos(lineNum,colno)
                return
            #如果视图是允许在大纲显示的视图类型,则跳转到指定行并选中对应的语法行
            if self.MainFrame.GetOutlineView().IsValidViewType(foundView):
                self.MainFrame.GetOutlineView().LoadOutLine(foundView, lineNum=lineNum)
    
    @property
    def OpenProjectPath(self):
        return self._open_project_path
        
    def GetPluginManager(self):
        """Returns the plugin manager used by this application
        @return: Apps plugin manager
        @see: L{plugin}

        """
        return self._pluginmgr
        
    def SetPluginManager(self,pluginmgr):
        self._pluginmgr = pluginmgr

    def AddMessageCatalog(self, name, path):
        """Add a catalog lookup path to the app
        @param name: name of catalog (i.e 'projects')
        @param path: catalog lookup path

        """
        if self.locale is not None:
            path = resource_filename(path, 'locale')
            self.locale.AddCatalogLookupPathPrefix(path)
            self.locale.AddCatalog(name)
        
    def _InitMenu(self):
        self._menu_bar = menu.MenuBar(self)
        self.config(menu=self._menu_bar)
        self._menu_bar.GetFileMenu()
        self._menu_bar.GetEditMenu()
        self._menu_bar.GetViewMenu()
        self._menu_bar.GetFormatMenu()
        self._menu_bar.GetProjectMenu()
        self._menu_bar.GetRunMenu()
        self._menu_bar.GetToolsMenu()
        self._menu_bar.GetHelpMenu()
        
    @property
    def Menubar(self):
        return self._menu_bar
        
    def AddCommand(self,command_id,main_menu_name,command_label,handler,accelerator=None,image = None,include_in_toolbar = False,\
                   add_separator=False,kind=consts.NORMAL_MENU_ITEM_KIND,variable=None,tester=None,default_tester=False,\
                   default_command=False,skip_sequence_binding=False,extra_sequences=[],**extra_args):

        main_menu = self._menu_bar.GetMenu(main_menu_name)
        self.AddMenuCommand(command_id,main_menu,command_label,handler,accelerator,image,include_in_toolbar,\
                            add_separator,kind,variable,tester,default_tester,default_command,skip_sequence_binding,\
                            extra_sequences,**extra_args)
                            

    def InsertCommand(self,item_after_id,command_id,main_menu_name,command_label,handler,accelerator=None,image = None,\
                      add_separator=False,kind=consts.NORMAL_MENU_ITEM_KIND,variable=None,tester=None):

        main_menu = self._menu_bar.GetMenu(main_menu_name)
        accelerator = self.AddAcceleratorCommand(command_id,accelerator,handler,tester)
        main_menu.InsertAfter(item_after_id,command_id,command_label,handler=handler,img=image,accelerator=accelerator,\
                         kind=kind,variable=variable,tester=tester)
                            
    def AddAcceleratorCommand(self,command_id,accelerator,handler,tester,bell_when_denied = True,\
                              skip_sequence_binding=False,extra_sequences=[]):
        
        def dispatch(event=None):
            if not tester or tester():
                denied = False
                handler()
            else:
                #快捷键在菜单状态为灰时依然可执行菜单回调函数,故在此处屏蔽回调函数调用
                denied = True
                utils.get_logger().debug("Command %d execution denied",command_id)
                if bell_when_denied:
                    self.bell()
        #accelerator表示菜单上显示的快捷键,sequence表示tk内部绑定的真正快捷键组合,两者需要转换
        accelerator,sequence = self._menu_bar.keybinder.GetBinding(command_id,accelerator)
        #skip_sequence_binding表示是否全局绑定快捷键,对应某些快捷键tk内部已经绑定,无需再次绑定
        if sequence is not None and not skip_sequence_binding:
            #绑定快捷键操作,全局范围有效,而且快捷键对应方法自带一个event参数,所以必须把handler方法包装一下
            self.bind_all(sequence,dispatch, True)
            
        for extra_sequence in extra_sequences:
            self.bind_all(extra_sequence, dispatch, True)
        return accelerator

    def AddMenuCommand(self,command_id,menu,command_label,handler,accelerator=None,image = None,include_in_toolbar = False,add_separator=False,\
                kind=consts.NORMAL_MENU_ITEM_KIND,variable=None,tester=None,default_tester=False,default_command=False,\
                skip_sequence_binding=False,extra_sequences=[],**extra_args):
    
        '''
            tester表示菜单状态更新的回调函数,返回bool值
        '''
        
        if image is not None and type(image) == str:
            image = self.GetImage(image)
            
        if tester is None and default_tester:
            if default_command:
                self.AppendDefaultCommand(command_id)
            tester = lambda:self.UpdateUI(command_id)
            
        if add_separator:
            #使用pop方法,用完后删除此键,避免传入菜单add_command方法中去
            sep_location = extra_args.pop('separator_location','bottom')
        accelerator = self.AddAcceleratorCommand(command_id,accelerator,handler,tester,skip_sequence_binding=skip_sequence_binding,extra_sequences=extra_sequences)
        
        if add_separator and sep_location == "top":
            menu.add_separator()
        menu.Append(command_id,command_label,handler=handler,img=image,accelerator=accelerator,\
                         kind=kind,variable=variable,tester=tester,**extra_args)
        if add_separator and sep_location == "bottom":
            menu.add_separator()
        if include_in_toolbar:
            self.MainFrame.AddToolbarButton(command_id,image,command_label,handler,accelerator,tester=tester)

    def UpdateUI(self,command_id):
        #优先处理运行调试菜单,如果存在打开项目,状态应该为可用
        if command_id in [constants.ID_RUN,constants.ID_DEBUG]:
            if self.MainFrame.GetProjectView(False).GetCurrentProject() is not None:
                return True
             
        active_view = self.GetDocumentManager().GetCurrentView()
        if command_id in self._default_command_ids:
            if self.MainFrame.GetNotebook().get_current_editor() is None or active_view is None:
                return False
        
        assert(active_view is not None)
        return active_view.UpdateUI(command_id)
            
    def _InitCommands(self):
        self.AddCommand(constants.ID_NEW,_("&File"),_("&New..."),self.OnNew,image="toolbar/new.png",include_in_toolbar=True)
        self.AddCommand(constants.ID_OPEN,_("&File"),_("&Open..."),self.OnOpen,image="toolbar/open.png",include_in_toolbar=True)
        self.AddCommand(constants.ID_CLOSE,_("&File"),_("&Close"),self.OnClose,default_tester=True,default_command=True)
        self.AddCommand(constants.ID_CLOSE_ALL,_("&File"),_("&Close A&ll"),self.OnCloseAll,add_separator=True,default_tester=True,default_command=True)

        self.AddCommand(constants.ID_SAVE,_("&File"),_("&Save..."),self.OnFileSave,image="toolbar/save.png",include_in_toolbar=True,default_tester=True,default_command=True)
        self.AddCommand(constants.ID_SAVEAS,_("&File"),_("Save &As..."),self.OnFileSaveAs,default_tester=True,default_command=True)
        
        self.AddCommand(constants.ID_SAVEALL,_("&File"),_("Save All"),self.OnFileSaveAll,image="toolbar/saveall.png",\
                    include_in_toolbar=True,add_separator=True,tester=self.MainFrame.GetNotebook().SaveAllFilesEnabled)
                    
        self.AddCommand(constants.ID_EXIT,_("&File"),_("E&xit"),self.Quit,image="exit.png")###accelerator="Ctrl+X"
        
        #设置历史文件菜单为Files菜单
        self.GetDocumentManager().FileHistoryUseMenu(self._menu_bar.GetFileMenu())
        #加载历史文件记录到Files菜单最后
        self.GetDocumentManager().FileHistoryAddFilesToMenu()
        self.MainFrame._InitCommands()
        self.InitThemeMenu()

        self.AddCommand(constants.ID_RUN,_("&Run"),_("&Start Running"),self.Run,image="toolbar/run.png",include_in_toolbar=True,default_tester=True,default_command=True)
        self.AddCommand(constants.ID_DEBUG,_("&Run"),_("&Start Debugging"),self.DebugRun,image="toolbar/debug.png",include_in_toolbar=True,default_tester=True,default_command=True)
        self.AddCommand(constants.ID_OPEN_TERMINAL,_("&Tools"),_("&Terminator"),self.OpenTerminator,image="cmd.png")
        self.AddCommand(constants.ID_CHECK_UPDATE,_("&Help"),_("&Check for Updates"),handler=lambda:self.CheckUpdate(ignore_error=False))
        self.AddCommand(constants.ID_GOTO_OFFICIAL_WEB,_("&Help"),_("&Visit NovalIDE Website"),self.GotoWebsite)
    
    def Run(self):
        raise Exception("This method must be implemented in derived class")
        
    def DebugRun(self):
        raise Exception("This method must be implemented in derived class")
        
    def OpenTerminator(self):
        if utils.is_windows():
            subprocess.Popen('start cmd.exe',shell=True)
        else:
            subprocess.Popen('gnome-terminal',shell=True)
        
    def GetImage(self,file_name):
        return imageutils.load_image("",file_name)

    def _InitMainFrame(self):
        self.frame = frame.DocTabbedParentFrame(self,None, None, -1, self.GetAppName(),tk.NSEW)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        
    @property
    def MainFrame(self):
        return self.frame
        
    @misc.update_toolbar
    def OnOpen(self):
        self.GetDocumentManager().CreateDocument('',core.DEFAULT_DOCMAN_FLAGS)
        
    def OnNew(self):
        self.GetDocumentManager().CreateDocument('',core.DOC_NEW)
        
    @misc.update_toolbar
    def OnClose(self):
        self.MainFrame.CloseDoc()
        
    @misc.update_toolbar
    def OnCloseAll(self):
        self.MainFrame.CloseAllDocs()

    @misc.update_toolbar
    def OnFileSave(self):
        """
        Saves the current document by calling wxDocument.Save for the current
        document.
        """
        doc = self.GetDocumentManager().GetCurrentDocument()
        if not doc:
            return
        doc.Save()

    @misc.update_toolbar
    def OnFileSaveAs(self):
        """
        Calls wxDocument.SaveAs for the current document.
        """
        doc = self.GetDocumentManager().GetCurrentDocument()
        if not doc:
            return
        self.SaveAsDocument(doc)
        
    def SaveAsDocument(self,doc):
        '''
            另存为文件
        '''
        #另存文件之前的文件名
        old_filename = doc.GetFilename()
        if not doc.SaveAs():
            return
        #另存文件之后的文件名
        new_filename = doc.GetFilename()
        #比较另存文件之前和之后的文件名,如果不一致,则从监视中删除先前的文件,并监视新的文件名
        if doc.IsWatched and not parserutils.ComparePath(new_filename,old_filename):
            doc.FileWatcher.RemoveFile(old_filename)

    @misc.update_toolbar
    def OnFileSaveAll(self):
        """
        Saves all of the currently open documents.
        """
        docs = self.GetDocumentManager().GetDocuments()
        # save child documents first
        for doc in docs:
            doc.Save()
        
    def GetDefaultEditorFamily(self):
        default_editor_family = consts.DEFAULT_FONT_FAMILY
        families = tk_font.families()
        for family in ["Consolas", "Ubuntu Mono", "Menlo", "DejaVu Sans Mono"]:
            if family in families:
                default_editor_family = family
                break
        return default_editor_family

    def _InitFonts(self):
        default_editor_family = self.GetDefaultEditorFamily()
        default_io_family = consts.DEFAULT_FONT_FAMILY
        default_font = tk_font.nametofont("TkDefaultFont")
        
        if utils.is_linux():
            heading_font = tk_font.nametofont("TkHeadingFont")
            heading_font.configure(weight="normal")
            caption_font = tk_font.nametofont("TkCaptionFont")
            caption_font.configure(weight="normal", size=default_font.cget("size"))

        self._fonts = [
            tk_font.Font(name="IOFont", family=utils.profile_get(consts.IO_FONT_FAMILY_KEY,default_io_family)),
            tk_font.Font(
                name="EditorFont", family=utils.profile_get(consts.EDITOR_FONT_FAMILY_KEY,default_editor_family)
            ),
            tk_font.Font(
                name="SmallEditorFont",
                family=utils.profile_get(consts.EDITOR_FONT_FAMILY_KEY,default_editor_family),
            ),
            tk_font.Font(
                name="BoldEditorFont",
                family=utils.profile_get(consts.EDITOR_FONT_FAMILY_KEY,default_editor_family),
                weight="bold",
            ),
            tk_font.Font(
                name="ItalicEditorFont",
                family=utils.profile_get(consts.EDITOR_FONT_FAMILY_KEY,default_editor_family),
                slant="italic",
            ),
            tk_font.Font(
                name="BoldItalicEditorFont",
                family=utils.profile_get(consts.EDITOR_FONT_FAMILY_KEY,default_editor_family),
                weight="bold",
                slant="italic",
            ),
            tk_font.Font(
                name=consts.TREE_VIEW_FONT,
                family=default_font.cget("family"),
                size=default_font.cget("size"),
            ),
            tk_font.Font(
                name="TreeviewBoldFont",
                family=default_font.cget("family"),
                size=default_font.cget("size"),
                weight="bold",
            ),
            
            tk_font.Font(
                name="BoldTkDefaultFont",
                family=default_font.cget("family"),
                size=default_font.cget("size"),
                weight="bold",
            ),
            tk_font.Font(
                name="ItalicTkDefaultFont",
                family=default_font.cget("family"),
                size=default_font.cget("size"),
                slant="italic",
            ),
            tk_font.Font(
                name="UnderlineTkDefaultFont",
                family=default_font.cget("family"),
                size=default_font.cget("size"),
                underline=1,
            ),
        ]
        self.UpdateFonts()
        
    def UpdateFonts(self):
        default_editor_family = self.GetDefaultEditorFamily()
        editor_font_size = self._guard_font_size(
            utils.profile_get_int(consts.EDITOR_FONT_SIZE_KEY,consts.DEFAULT_FONT_SIZE)
        )
        editor_font_family = utils.profile_get(consts.EDITOR_FONT_FAMILY_KEY,default_editor_family)
        io_font_family = utils.profile_get(consts.IO_FONT_FAMILY_KEY,default_editor_family)

        tk_font.nametofont("IOFont").configure(
            family=io_font_family,
            size=min(editor_font_size - 2, int(editor_font_size * 0.8 + 3)),
        )
        tk_font.nametofont("EditorFont").configure(
            family=editor_font_family, size=editor_font_size
        )
        tk_font.nametofont("SmallEditorFont").configure(
            family=editor_font_family, size=editor_font_size - 2
        )
        tk_font.nametofont("BoldEditorFont").configure(
            family=editor_font_family, size=editor_font_size
        )
        tk_font.nametofont("ItalicEditorFont").configure(
            family=editor_font_family, size=editor_font_size
        )
        tk_font.nametofont("BoldItalicEditorFont").configure(
            family=editor_font_family, size=editor_font_size
        )
        style = ttk.Style()
        treeview_font_size = int(editor_font_size * 0.7 + 2)
        rowheight = 20
        tk_font.nametofont(consts.TREE_VIEW_FONT).configure(size=treeview_font_size)
        tk_font.nametofont(consts.TREE_VIEW_BOLD_FONT).configure(size=treeview_font_size)
        style.configure("Treeview", rowheight=rowheight)

       # if self._editor_notebook is not None:
        #    self._editor_notebook.update_appearance()
        
    def _guard_font_size(self, size):
        MIN_SIZE = 4
        MAX_SIZE = 200
        if size < MIN_SIZE:
            return MIN_SIZE
        elif size > MAX_SIZE:
            return MAX_SIZE
        else:
            return size
            
    def AllowClose(self):
        #先查询是否允许关闭所有窗口
        if not self.MainFrame.CloseWindows():
            return False
        if not self.GetDocumentManager().Clear():
            return False
            
    ##    self.MainFrame.destroy()
        return True

    def SaveLayout(self):
        #退出时保存窗口是否最大化的标志
        utils.profile_set(consts.FRAME_MAXIMIZED_KEY, misc.get_zoomed(self))
        if not misc.get_zoomed(self):
            # can't restore zoom on mac without setting actual dimensions
            utils.profile_set(consts.FRAME_TOP_LOC_KEY, self.winfo_y())
            utils.profile_set(consts.FRAME_LEFT_LOC_KEY, self.winfo_x())
            utils.profile_set(consts.FRAME_WIDTH_KEY, self.winfo_width())
            utils.profile_set(consts.FRAME_HEIGHT_KEY, self.winfo_height())
            
        self.MainFrame.SaveLayout()
        
    def Quit(self):
        self.update_idletasks()
        UserDataDb().RecordEnd()
        self.SaveLayout()
        docposition.DocMgr.WriteBook()
        core.App.Quit(self)

    def OpenMRUFile(self, n):
        """
        Opens the appropriate file when it is selected from the file history
        menu.
        """
        filename = self._docManager.GetHistoryFile(n)
        if filename and os.path.exists(filename):
            self._docManager.CreateDocument(filename, core.DOC_SILENT)
        else:
            self._docManager.RemoveFileFromHistory(n)
            msgTitle = self.GetAppName()
            if not msgTitle:
                msgTitle = _("File Error")
            if filename:
                messagebox.showerror(msgTitle,_("The file '%s' doesn't exist and couldn't be opened!") % filename)

    def event_generate(self, sequence, event = None, **kwargs) :
        """Uses custom event handling when sequence doesn't start with <.
        In this case arbitrary attributes can be added to the event.
        Otherwise forwards the call to Tk's event_generate"""
        # pylint: disable=arguments-differ
        if sequence.startswith("<"):
            assert event is None
            tk.Tk.event_generate(self, sequence, **kwargs)
        else:
            if sequence in self._event_handlers:
                if event is None:
                    event = AppEvent(sequence, **kwargs)
                else:
                    event.update(kwargs)

                # make a copy of handlers, so that event handler can remove itself
                # from the registry during iteration
                # (or new handlers can be added)
                for handler in sorted(self._event_handlers[sequence].copy(), key=str):
                    try:
                        handler(event)
                    except Exception:
                        utils.get_logger().exception("Problem when handling '" + sequence + "'")
        self.MainFrame.UpdateToolbar()

    def bind(self, sequence, func, add = None):
        """Uses custom event handling when sequence doesn't start with <.
        Otherwise forwards the call to Tk's bind"""
        # pylint: disable=signature-differs
        if not add:
            logging.warning(
                "Workbench.bind({}, ..., add={}) -- did you really want to replace existing bindings?".format(
                    sequence, add
                )
            )
        #tk内部事件
        if sequence.startswith("<"):
            tk.Tk.bind(self, sequence, func, add)
        else:
            #程序自定义事件,不能以<开头
            if sequence not in self._event_handlers or not add:
                self._event_handlers[sequence] = set()

            self._event_handlers[sequence].add(func)
            
    def SetCurrentProject(self):
        self.MainFrame.GetProjectView().SetCurrentProject()
        
    def add_ui_theme(self,name,parent,settings,images={}):
        if name in self._ui_themes:
            utils.get_logger().warn("Overwriting theme '%s'" ,name)

        self._ui_themes[name] = (parent, settings, images)
        
        if parent is not None:
            pass

    def _init_theming(self):
        self._style = ttk.Style()
        self._ui_themes = (
            {}
        )  # type: Dict[str, Tuple[Optional[str], FlexibleUiThemeSettings, Dict[str, str]]] # value is (parent, settings, images)
        self._syntax_themes = (
            {}
        )  # type: Dict[str, Tuple[Optional[str], FlexibleSyntaxThemeSettings]] # value is (parent, settings)
        # following will be overwritten by plugins.base_themes
       # self.set_default(
        #    "view.ui_theme", "xpnative" if running_on_windows() else "clam"
        #)
        #self.set_default(
         #   "view.ui_theme", "xpnative" if running_on_windows() else "clam"
        #)
        
        self.theme_value = tk.StringVar()
        self.theme_value.set(consts.WINDOWS_UI_THEME_NAME)

    def _register_ui_theme_as_tk_theme(self, name):
        # collect settings from all ancestors
        total_settings = []  # type: List[FlexibleUiThemeSettings]
        total_images = {}  # type: Dict[str, str]
        temp_name = name
        while True:
            parent, settings, images = self._ui_themes[temp_name]
            total_settings.insert(0, settings)
            for img_name in images:
                total_images.setdefault(img_name, images[img_name])

            if parent is not None:
                temp_name = parent
            else:
                # reached start of the chain
                break

        assert temp_name in self._style.theme_names()
        # only root of the ancestors is relevant for theme_create,
        # because the method actually doesn't take parent settings into account
        # (https://mail.python.org/pipermail/tkinter-discuss/2015-August/003752.html)
        self._style.theme_create(name, temp_name)
      #  self._image_mapping_by_theme[name] = total_images

        #加载编辑器标签页右上角的关闭图标
        self.MainFrame.GetNotebook().images.append(imageutils.load_image("img_close","tab-close.gif"))
        self.MainFrame.GetNotebook().images.append(imageutils.load_image("img_close_active","tab-close-active.gif"))

        # apply settings starting from root ancestor
        for settings in total_settings:
            if callable(settings):
                settings = settings()

            if isinstance(settings, dict):
                self._style.theme_settings(name, settings)
            else:
                for subsettings in settings:
                    self._style.theme_settings(name, subsettings)

    def _apply_ui_theme(self, name):
        self._current_theme_name = name
        print (name,self._style.theme_names(),self._style.theme_use())
        if name not in self._style.theme_names():
            self._register_ui_theme_as_tk_theme(name)

        self._style.theme_use(name)

        # https://wiki.tcl.tk/37973#pagetocfe8b22ab
        for setting in [
            "background",
            "foreground",
            "selectBackground",
            "selectForeground",
        ]:
            value = self._style.lookup("Listbox", setting)
            if value:
                self.option_add("*TCombobox*Listbox." + setting, value)
                self.option_add("*Listbox." + setting, value)

        text_opts = self._style.configure("Text")
        if text_opts:
            for key in text_opts:
                self.option_add("*Text." + key, text_opts[key])

     
        #更新菜单栏的菜单
        for menu_data in self.Menubar._menus:
            menu = menu_data[2]
            menu.configure(misc.get_style_configuration("Menu"))

     #   self.update_fonts()
        
    def get_usable_ui_theme_names(self):
        return sorted(
            [name for name in self._ui_themes if self._ui_themes[name][0] is not None]
        )
    
    def InitThemeMenu(self):
        theme_names = self.get_usable_ui_theme_names()
        if len(theme_names):
            view_menu = self.Menubar.GetMenu(_("&View"))
            theme_menu = tkmenu.PopupMenu()
            view_menu.AppendMenu(constants.ID_VIEW_APPLICAITON_LOOK,_("&Application Look"),theme_menu)
            for name in theme_names:
                def apply_theme(name=name):
                    self._apply_ui_theme(name)
                self.AddMenuCommand(name,theme_menu,command_label=name,handler=apply_theme,\
                            kind = consts.RADIO_MENU_ITEM_KIND,variable=self.theme_value,value=name)
                            
    def GotoWebsite(self,):
        os.startfile(UserDataDb.HOST_SERVER_ADDR)
        
    def GetInterpreterManager(self):
        return InterpreterManager.InterpreterManager()
        
    def OnOptions(self):
        preference_dlg = preference.PreferenceDialog(self)
        preference_dlg.ShowModal()

class AppEvent(record.Record):
    def __init__(self, sequence, **kwargs):
        record.Record.__init__(self, **kwargs)
        self.sequence = sequence