#----------------------------------------------------------------------------
# Name:         PythonEditor.py
# Purpose:      PythonEditor for wx.lib.pydocview tbat uses the Styled Text Control
#
# Author:       Peter Yared
#
# Created:      8/15/03
# CVS-ID:       $Id$
# Copyright:    (c) 2004-2005 ActiveGrid, Inc.
# License:      wxWindows License
#----------------------------------------------------------------------------

import CodeEditor
import wx
import wx.lib.docview
import wx.lib.pydocview
import string
import keyword  # So it knows what to hilite
import wx.py  # For the Python interpreter
import wx.stc # For the Python interpreter
import StringIO  # For indent
import OutlineService
import STCTextEditor
import keyword # for GetAutoCompleteKeywordList
import sys # for GetAutoCompleteKeywordList
import MessageService # for OnCheckCode
import OutlineService
import FindInDirService
import codecs
import noval.parser.config as parserconfig
import Service
import noval.parser.fileparser as parser
import noval.parser.scope as scope
import Interpreter
import InterpreterConfigDialog
import noval.parser.intellisence as intellisence
import noval.parser.nodeast as nodeast
import noval.util.strutils as strutils
import CompletionService
import DebuggerService
from noval.parser.utils import CmpMember
from noval.util.logger import app_debugLogger
try:
    import checker # for pychecker
    _CHECKER_INSTALLED = True
except ImportError:
    _CHECKER_INSTALLED = False
import os.path # for pychecker
_ = wx.GetTranslation

VIEW_PYTHON_INTERPRETER_ID = wx.NewId()

class RunParameter():
    def __init__(self,arg,env,start_up):
        self.Arg = arg
        self.Environment = env
        self.StartUp = start_up

class PythonDocument(CodeEditor.CodeDocument): 

    UTF_8_ENCODING = 0
    GBK_ENCODING = 1
    ANSI_ENCODING = 2

    def get_coding_spec(self,lines):
        """Return the encoding declaration according to PEP 263.
        Raise LookupError if the encoding is declared but unknown.
        """
        name,_ = strutils.get_python_coding_declare(lines)
        if name is None:
            return None
        # Check whether the encoding is known
        try:
            codecs.lookup(name)
        except LookupError:
            # The standard encoding error does not indicate the encoding
            raise LookupError, "Unknown encoding " + name
        return name

    def DoSaveBefore(self):
        CodeEditor.CodeDocument.DoSaveBefore(self)
        view = self.GetFirstView()
        lines = view.GetTopLines(3)
        declare_encoding = self.get_coding_spec(lines)
        if None == declare_encoding:
            declare_encoding = CodeEditor.CodeDocument.DEFAULT_FILE_ENCODING
        if self.IsDocEncodingChanged(declare_encoding):
            self.file_encoding = declare_encoding
    
    def DoSaveBehind(self):
        pass
        
    def GetDocEncoding(self,encoding):
        lower_encoding = encoding.lower() 
        if lower_encoding == "utf-8" or lower_encoding == "utf-8-sig":
            return self.UTF_8_ENCODING
        elif lower_encoding == "gbk" or lower_encoding == "gb2312" \
             or lower_encoding == "gb18030" or lower_encoding == "cp936":
            return self.GBK_ENCODING
        return self.ANSI_ENCODING

    def IsUtf8Doc(self,encoding):
        if encoding.lower().find("utf-8"):
            return True
        return False

    def IsDocEncodingChanged(self,encoding):
        if self.GetDocEncoding(encoding) != self.GetDocEncoding(self.file_encoding):
            return True
        return False

class PythonView(CodeEditor.CodeView):

    def __init__(self):
        super(PythonView,self).__init__()
        self._module_scope = None
        self._run_parameter = None
        #document checksum to check document is updated
        self._checkSum = -1

    def SetRunParameter(self,arg,start_up,env):
        self._run_parameter = RunParameter(arg,env,start_up)

    @property
    def RunParameter(self):
        return self._run_parameter
        
    @property
    def ModuleScope(self):
        return self._module_scope

    def LoadModule(self,filename,doc_update):
        if not doc_update:
            return

        module = parser.parse_content(self.GetCtrl().GetValue(),filename)
        if module is None:
            return
        module_scope = scope.ModuleScope(module,self.GetCtrl().GetLineCount())
        module_scope.MakeModuleScopes()
        module_scope.RouteChildScopes()
        self.ModuleScope = module_scope
        
    @ModuleScope.setter
    def ModuleScope(self,module_scope):
        self._module_scope = module_scope
        
    def GetCtrlClass(self):
        """ Used in split window to instantiate new instances """
        return PythonCtrl
    
    def GetLangLexer(self):
        return parserconfig.LANG_PYTHON_LEXER

    def ProcessUpdateUIEvent(self, event):
        if not self.GetCtrl():
            return False
            
        id = event.GetId()
        if id == CodeEditor.CHECK_CODE_ID:
            hasText = self.GetCtrl().GetTextLength() > 0
            event.Enable(hasText)
            return True
            
        return CodeEditor.CodeView.ProcessUpdateUIEvent(self, event)


    def OnActivateView(self, activate, activeView, deactiveView):
        STCTextEditor.TextView.OnActivateView(self, activate, activeView, deactiveView)
        if activate and self.GetCtrl():
            if self.GetDocumentManager().GetFlags() & wx.lib.docview.DOC_SDI:
                self.LoadOutline()
            else:
                wx.CallAfter(self.LoadOutline)  # need CallAfter because document isn't loaded yet
        

    def OnClose(self, deleteWindow = True):
        status = STCTextEditor.TextView.OnClose(self, deleteWindow)
        wx.CallAfter(self.ClearOutline)  # need CallAfter because when closing the document, it is Activated and then Close, so need to match OnActivateView's CallAfter
        return status
       

    def GetAutoCompleteKeywordList(self, context, hint,line):
        obj = None
        try:
            if context and len(context):
                obj = eval(context, globals(), locals())
        except:
            if not hint or len(hint) == 0:  # context isn't valid, maybe it was the hint
                hint = context
            
        if obj is None:
            kw = keyword.kwlist[:]
            module_scope = self.ModuleScope
            members = []
            if module_scope is not None:
                scope = module_scope.FindScope(line)
                parent = scope
                while parent is not None:
                    if parent.Parent is None:
                        members.extend(parent.GetMembers())
                    else:
                        members.extend(parent.GetMemberList(False))
                    parent = parent.Parent
                kw.extend(members)
                builtin_members = intellisence.IntellisenceManager().GetBuiltinModuleMembers()
                kw.extend(builtin_members)
        else:
            symTbl = dir(obj)
            kw = filter(lambda item: item[0] != '_', symTbl)  # remove local variables and methods
        
        if hint and len(hint):
            lowerHint = hint.lower()
            filterkw = filter(lambda item: item.lower().startswith(lowerHint), kw)  # remove variables and methods that don't match hint
            kw = filterkw

        kw.sort(CmpMember)
        if hint:
            replaceLen = len(hint)
        else:
            replaceLen = 0
        return " ".join(kw), replaceLen


    def OnCheckCode(self):
        if not _CHECKER_INSTALLED:       
            wx.MessageBox(_("pychecker not found.  Please install pychecker."), _("Check Code"))
            return

        filename = os.path.basename(self.GetDocument().GetFilename())

        # pychecker only works on files, doesn't take a stream or string input
        if self.GetDocument().IsModified():
            dlg = wx.MessageDialog(self.GetFrame(), _("'%s' has been modfied and must be saved first.  Save file and check code?") % filename, _("Check Code"))
            dlg.CenterOnParent()
            val = dlg.ShowModal()
            dlg.Destroy()
            if val == wx.ID_OK:
                self.GetDocument().Save()
            else:
                return
            
        messageService = wx.GetApp().GetService(MessageService.MessageService)
        messageService.ShowWindow()
        view = messageService.GetView()
        if not view:
            return
            
        view.ClearLines()
        view.SetCallback(self.OnJumpToFoundLine)
        
        # Set cursor to Wait cursor
        wx.GetApp().GetTopWindow().SetCursor(wx.StockCursor(wx.CURSOR_WAIT))

        try:
            # This takes a while for involved code
            checker.checkSyntax(self.GetDocument().GetFilename(), view)

        finally:
            # Set cursor to Default cursor
            wx.GetApp().GetTopWindow().SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))


    def OnJumpToFoundLine(self, event):
        messageService = wx.GetApp().GetService(MessageService.MessageService)
        lineText, pos = messageService.GetView().GetCurrLine()
        
        lineEnd = lineText.find(".py:")
        if lineEnd == -1:
            return

        lineStart = lineEnd + len(".py:")
        lineEnd = lineText.find(":", lineStart)
        lineNum = int(lineText[lineStart:lineEnd])

        filename = lineText[0:lineStart - 1]

        foundView = None
        openDocs = wx.GetApp().GetDocumentManager().GetDocuments()
        for openDoc in openDocs:
            if openDoc.GetFilename() == filename:
                foundView = openDoc.GetFirstView()
                break

        if not foundView:
            doc = wx.GetApp().GetDocumentManager().CreateDocument(filename, wx.lib.docview.DOC_SILENT|wx.lib.docview.DOC_OPEN_ONCE)
            foundView = doc.GetFirstView()

        if foundView:
            foundView.GetFrame().SetFocus()
            foundView.Activate()
            foundView.GotoLine(lineNum)
            startPos = foundView.PositionFromLine(lineNum)
            endPos = foundView.GetLineEndPosition(lineNum)
            # wxBug:  Need to select in reverse order, (end, start) to put cursor at head of line so positioning is correct
            #         Also, if we use the correct positioning order (start, end), somehow, when we open a edit window for the first
            #         time, we don't see the selection, it is scrolled off screen
            foundView.SetSelection(endPos, startPos)
            wx.GetApp().GetService(OutlineService.OutlineService).LoadOutline(foundView, position=startPos)

    def DoLoadOutlineCallback(self, force=False):
        outlineService = wx.GetApp().GetService(OutlineService.OutlineService)
        if not outlineService:
            return False

        outlineView = outlineService.GetView()
        if not outlineView:
            return False

        treeCtrl = outlineView.GetTreeCtrl()
        if not treeCtrl:
            return False

        view = treeCtrl.GetCallbackView()
        newCheckSum = self.GenCheckSum()
        doc_update = self._checkSum != newCheckSum
        if not force:
            if view and view is self:
                if self._checkSum == newCheckSum:
                    return False
        self._checkSum = newCheckSum
        document = self.GetDocument()
        if not document:
            return True
        filename = document.GetFilename()
        self.LoadModule(filename,doc_update)
        if self.ModuleScope == None:
            if view is None or filename != view.GetDocument().GetFilename():
                treeCtrl.DeleteAllItems()
            return True
        #should freeze control to prevent update and treectrl flick
        treeCtrl.Freeze()
        treeCtrl.DeleteAllItems()
        rootItem = treeCtrl.AddRoot(self.ModuleScope.Module.Name)
        treeCtrl.SetItemImage(rootItem,treeCtrl.moduleidx,wx.TreeItemIcon_Normal)
        treeCtrl.SetDoSelectCallback(rootItem, self, self.ModuleScope.Module)
        self.TranverseItem(treeCtrl,self.ModuleScope.Module,rootItem)
        treeCtrl.Expand(rootItem)
        #use thaw to update freezw control
        treeCtrl.Thaw()
        return True
           
    def TranverseItem(self,treeCtrl,node,parent):
        for child in node.Childs:
            if child.Type == parserconfig.NODE_FUNCDEF_TYPE:
                item_image_index = 1
                item = treeCtrl.AppendItem(parent, child.Name)
                treeCtrl.SetItemImage(item,item_image_index,wx.TreeItemIcon_Normal)
                treeCtrl.SetDoSelectCallback(item, self, child)
            elif child.Type == parserconfig.NODE_CLASSDEF_TYPE:
                item_image_index = 2
                item = treeCtrl.AppendItem(parent, child.Name)
                treeCtrl.SetItemImage(item,item_image_index,wx.TreeItemIcon_Normal)
                treeCtrl.SetDoSelectCallback(item, self, child)
                self.TranverseItem(treeCtrl,child,item)
            elif child.Type == parserconfig.NODE_OBJECT_PROPERTY or \
                        child.Type == parserconfig.NODE_ASSIGN_TYPE:
                item_image_index = 3
                item = treeCtrl.AppendItem(parent, child.Name)
                treeCtrl.SetItemImage(item,item_image_index,wx.TreeItemIcon_Normal)
                treeCtrl.SetDoSelectCallback(item, self, child)
            elif child.Type == parserconfig.NODE_IMPORT_TYPE:
                item_image_index = 4
                name = child.Name
                if child.AsName is not None:
                    name = child.AsName
                item = treeCtrl.AppendItem(parent,name)
                treeCtrl.SetItemImage(item,item_image_index,wx.TreeItemIcon_Normal)
                treeCtrl.SetDoSelectCallback(item, self, child)
            elif child.Type == parserconfig.NODE_FROMIMPORT_TYPE:
                item_image_index = 5
                from_import_item = treeCtrl.AppendItem(parent,child.Name)
                treeCtrl.SetItemImage(from_import_item,item_image_index,wx.TreeItemIcon_Normal)
                treeCtrl.SetDoSelectCallback(from_import_item, self, child)
                for node_import in child.Childs:
                    item_image_index = 4
                    name = node_import.Name
                    if node_import.AsName is not None:
                        name = node_import.AsName
                    import_item = treeCtrl.AppendItem(from_import_item,name)
                    treeCtrl.SetItemImage(import_item,item_image_index,wx.TreeItemIcon_Normal)
                    treeCtrl.SetDoSelectCallback(import_item, self, node_import)

    def IsUnitTestEnable(self):
        return True

class PythonInterpreterView(Service.ServiceView):

    def _CreateControl(self, parent, id):
        sizer = wx.BoxSizer()
        self._pyCrust = wx.py.crust.Crust(parent)
        self._pyCrust._shouldsplit = False
        sizer.Add(self._pyCrust, 1, wx.EXPAND, 0)
        return self._pyCrust
        
    def GetDocument(self):
        return None

    def OnFocus(self, event):
        wx.GetApp().GetDocumentManager().ActivateView(self)
        event.Skip()        

    def ProcessEvent(self, event):
        if not hasattr(self, "_pyCrust") or not self._pyCrust:
            return wx.lib.docview.View.ProcessEvent(self, event)
        stcControl = wx.Window_FindFocus()
        if not isinstance(stcControl, wx.stc.StyledTextCtrl):
            return wx.lib.docview.View.ProcessEvent(self, event)
        id = event.GetId()
        if id == wx.ID_UNDO:
            stcControl.Undo()
            return True
        elif id == wx.ID_REDO:
            stcControl.Redo()
            return True
        elif id == wx.ID_CUT:
            stcControl.Cut()
            return True
        elif id == wx.ID_COPY:
            stcControl.Copy()
            return True
        elif id == wx.ID_PASTE:
            stcControl.Paste()
            return True
        elif id == wx.ID_CLEAR:
            stcControl.Clear()
            return True
        elif id == wx.ID_SELECTALL:
            stcControl.SetSelection(0, -1)
            return True
        else:
            return wx.lib.docview.View.ProcessEvent(self, event)


    def ProcessUpdateUIEvent(self, event):
        if not hasattr(self, "_pyCrust") or not self._pyCrust:
            return wx.lib.docview.View.ProcessUpdateUIEvent(self, event)
        stcControl = wx.Window_FindFocus()
        if not isinstance(stcControl, wx.stc.StyledTextCtrl):
            return wx.lib.docview.View.ProcessUpdateUIEvent(self, event)
        id = event.GetId()
        if id == wx.ID_UNDO:
            event.Enable(stcControl.CanUndo())
            return True
        elif id == wx.ID_REDO:
            event.Enable(stcControl.CanRedo())
            return True
        elif id == wx.ID_CUT:
            event.Enable(stcControl.CanCut())
            return True
        elif id == wx.ID_COPY:
            event.Enable(stcControl.CanCopy())
            return True
        elif id == wx.ID_PASTE:
            event.Enable(stcControl.CanPaste())
            return True
        elif id == wx.ID_CLEAR:
            event.Enable(True)  # wxBug: should be stcControl.CanCut()) but disabling clear item means del key doesn't work in control as expected
            return True
        elif id == wx.ID_SELECTALL:
            event.Enable(stcControl.GetTextLength() > 0)
            return True
        else:
            return wx.lib.docview.View.ProcessUpdateUIEvent(self, event)


    def OnClose(self, deleteWindow=True):
        if deleteWindow and self.GetFrame():
            self.GetFrame().Destroy()
        return True


class PythonInterpreterDocument(wx.lib.docview.Document):
    """ Generate Unique Doc Type """
    pass
    

class PythonService(Service.Service):

    #----------------------------------------------------------------------------
    # Overridden methods
    #----------------------------------------------------------------------------

    def _CreateView(self):
        return PythonInterpreterView(self)

    def InstallControls(self, frame, menuBar = None, toolBar = None, statusBar = None, document = None):
        Service.Service.InstallControls(self, frame, menuBar, toolBar, statusBar, document)

        if document and document.GetDocumentTemplate().GetDocumentType() != PythonDocument:
            return
        if not document and wx.GetApp().GetDocumentManager().GetFlags() & wx.lib.docview.DOC_SDI:
            return

        #viewMenu = menuBar.GetMenu(menuBar.FindMenu(_("&View")))
        #viewStatusBarItemPos = self.GetMenuItemPos(viewMenu, wx.lib.pydocview.VIEW_STATUSBAR_ID)
        #viewMenu.InsertCheckItem(viewStatusBarItemPos + 1, VIEW_PYTHON_INTERPRETER_ID, _("Python &Interpreter"), _("Shows or hides the Python interactive window"))
        #wx.EVT_MENU(frame, VIEW_PYTHON_INTERPRETER_ID, frame.ProcessEvent)
        #wx.EVT_UPDATE_UI(frame, VIEW_PYTHON_INTERPRETER_ID, frame.ProcessUpdateUIEvent)

    def ProcessEvent(self, event):
        id = event.GetId()
        if id == VIEW_PYTHON_INTERPRETER_ID:
            self.OnViewPythonInterpreter(event)
            return True
        else:
            return Service.Service.ProcessEvent(self, event)


    def ProcessUpdateUIEvent(self, event):
        id = event.GetId()
        if id == VIEW_PYTHON_INTERPRETER_ID:
            event.Enable(True)
            docManager = wx.GetApp().GetDocumentManager()
            event.Check(False)
            for doc in docManager.GetDocuments():
                if isinstance(doc, PythonInterpreterDocument):
                    event.Check(True)
                    break
            return True
        else:
            return Service.Service.ProcessUpdateUIEvent(self, event)


    def OnViewPythonInterpreter(self, event):
        for doc in wx.GetApp().GetDocumentManager().GetDocuments():
            if isinstance(doc, PythonInterpreterDocument):
                doc.DeleteAllViews()
                return
                
        for template in self.GetDocumentManager().GetTemplates():
            if template.GetDocumentType() == PythonInterpreterDocument:
                newDoc = template.CreateDocument('', wx.lib.docview.DOC_SILENT|wx.lib.docview.DOC_OPEN_ONCE)
                if newDoc:
                    newDoc.SetDocumentName(template.GetDocumentName())
                    newDoc.SetDocumentTemplate(template)
                    newDoc.OnNewDocument()
                    newDoc.SetWriteable(False)
                    newDoc.GetFirstView().GetFrame().SetTitle(_("Python Interpreter"))
                break

    def GetIconIndex(self):
        return Service.ServiceView.InterpreterIconIndex


class PythonCtrl(CodeEditor.CodeCtrl):

    TypeKeyWords = "complex list tuple dict bool int long float True False None"

    def __init__(self, parent, id=-1, style=wx.NO_FULL_REPAINT_ON_RESIZE):
        CodeEditor.CodeCtrl.__init__(self, parent, id, style)
        self.SetProperty("tab.timmy.whinge.level", "1")
        self.SetProperty("fold.comment.python", "1")
        self.SetProperty("fold.quotes.python", "1")
        self.SetLexer(wx.stc.STC_LEX_PYTHON)
        self.SetStyleBits(7)
        self.SetKeyWords(0, string.join(keyword.kwlist))
        self.SetKeyWords(1, self.TypeKeyWords)
        self.Bind(wx.EVT_CHAR, self.OnChar)
        CodeEditor.CodeCtrl.SetMarginFoldStyle(self)

    def CreatePopupMenu(self):
        SYNCTREE_ID = wx.NewId()
        menu = CodeEditor.CodeCtrl.CreatePopupMenu(self)
      #  self.Bind(wx.EVT_MENU, self.OnPopFindDefinition, id=FINDDEF_ID)
       # menu.Insert(1, FINDDEF_ID, _("Find 'def'"))

        #self.Bind(wx.EVT_MENU, self.OnPopFindClass, id=FINDCLASS_ID)
        #menu.Insert(2, FINDCLASS_ID, _("Find 'class'"))
        menu.AppendSeparator()
        self.Bind(wx.EVT_MENU, self.OnPopSyncOutline, id=SYNCTREE_ID)
        item = wx.MenuItem(menu, SYNCTREE_ID, _("Find in Outline View"))
        menu.AppendItem(item)
        
        self.Bind(wx.EVT_MENU, self.OnGotoDefinition, id=CompletionService.CompletionService.GO_TO_DEFINITION)
        item = wx.MenuItem(menu, CompletionService.CompletionService.GO_TO_DEFINITION, \
                            _("Goto Definition\tF12"))
        wx.EVT_UPDATE_UI(self,CompletionService.CompletionService.GO_TO_DEFINITION, self.DSProcessUpdateUIEvent)
        menu.AppendItem(item)

        menu.Append(DebuggerService.DebuggerService.RUN_ID, _("&Run\tF5"))
        wx.EVT_MENU(self, DebuggerService.DebuggerService.RUN_ID, self.RunScript)

        menu.Append(DebuggerService.DebuggerService.DEBUG_ID, _("&Debug\tCtrl+F5"))
        wx.EVT_MENU(self, DebuggerService.DebuggerService.DEBUG_ID, self.DebugRunScript)
        
        return menu

    def DebugRunScript(self,event):
        wx.GetApp().GetService(DebuggerService.DebuggerService).DebugRunScript(event)
    
    def RunScript(self,event):
        wx.GetApp().GetService(DebuggerService.DebuggerService).RunScript(event)

    def OnPopFindDefinition(self, event):
        view = wx.GetApp().GetDocumentManager().GetCurrentView()
        if hasattr(view, "GetCtrl") and view.GetCtrl() and hasattr(view.GetCtrl(), "GetSelectedText"):
            pattern = view.GetCtrl().GetSelectedText().strip()
            if pattern:
                searchPattern = "def\s+%s" % pattern
                wx.GetApp().GetService(FindInDirService.FindInDirService).FindInProject(searchPattern)


    def OnPopFindClass(self, event):
        view = wx.GetApp().GetDocumentManager().GetCurrentView()
        if hasattr(view, "GetCtrl") and view.GetCtrl() and hasattr(view.GetCtrl(), "GetSelectedText"):
            definition = "class\s+%s"
            pattern = view.GetCtrl().GetSelectedText().strip()
            if pattern:
                searchPattern = definition % pattern
                wx.GetApp().GetService(FindInDirService.FindInDirService).FindInProject(searchPattern)


    def SetViewDefaults(self):
        CodeEditor.CodeCtrl.SetViewDefaults(self, configPrefix="Python", hasWordWrap=True, hasTabs=True, hasFolding=True)


    def GetFontAndColorFromConfig(self):
        return CodeEditor.CodeCtrl.GetFontAndColorFromConfig(self, configPrefix = "Python")


    def UpdateStyles(self):
        CodeEditor.CodeCtrl.UpdateStyles(self)

        if not self.GetFont():
            return

        faces = { 'font' : self.GetFont().GetFaceName(),
                  'size' : self.GetFont().GetPointSize(),
                  'size2': self.GetFont().GetPointSize() - 2,
                  'color' : "%02x%02x%02x" % (self.GetFontColor().Red(), self.GetFontColor().Green(), self.GetFontColor().Blue())
                  }

        # Python styles
        # White space
        self.StyleSetSpec(wx.stc.STC_P_DEFAULT, "face:%(font)s,fore:#000000,face:%(font)s,size:%(size)d" % faces)
        # Comment
        self.StyleSetSpec(wx.stc.STC_P_COMMENTLINE, "face:%(font)s,fore:#007F00,italic,face:%(font)s,size:%(size)d" % faces)
        # Number
        self.StyleSetSpec(wx.stc.STC_P_NUMBER, "face:%(font)s,fore:#007F7F,size:%(size)d" % faces)
        # String
        self.StyleSetSpec(wx.stc.STC_P_STRING, "face:%(font)s,fore:#7F007F,face:%(font)s,size:%(size)d" % faces)
        # Single quoted string
        self.StyleSetSpec(wx.stc.STC_P_CHARACTER, "face:%(font)s,fore:#7F007F,face:%(font)s,size:%(size)d" % faces)
        # Keyword
        self.StyleSetSpec(wx.stc.STC_P_WORD, "face:%(font)s,fore:#00007F,bold,size:%(size)d" % faces)
        # Keyword2
        self.StyleSetSpec(wx.stc.STC_P_WORD2, "face:%(font)s,fore:#000080,bold,size:%(size)d" % faces)
        # Triple quotes
        self.StyleSetSpec(wx.stc.STC_P_TRIPLE, "face:%(font)s,fore:#7F0000,size:%(size)d" % faces)
        # Triple double quotes
        self.StyleSetSpec(wx.stc.STC_P_TRIPLEDOUBLE, "face:%(font)s,fore:#7F0000,size:%(size)d" % faces)
        # Class name definition
        self.StyleSetSpec(wx.stc.STC_P_CLASSNAME, "face:%(font)s,fore:#0000FF,bold,size:%(size)d" % faces)
        # Function or method name definition
        self.StyleSetSpec(wx.stc.STC_P_DEFNAME, "face:%(font)s,fore:#007F7F,bold,size:%(size)d" % faces)
        # Operators
        self.StyleSetSpec(wx.stc.STC_P_OPERATOR, "face:%(font)s,size:%(size)d" % faces)
        # Identifiers
        self.StyleSetSpec(wx.stc.STC_P_IDENTIFIER, "face:%(font)s,fore:#%(color)s,face:%(font)s,size:%(size)d" % faces)
        # Comment-blocks
        self.StyleSetSpec(wx.stc.STC_P_COMMENTBLOCK, "face:%(font)s,fore:#7F7F7F,size:%(size)d" % faces)
        # End of line where string is not closed
        self.StyleSetSpec(wx.stc.STC_P_STRINGEOL, "face:%(font)s,fore:#000000,face:%(font)s,back:#E0C0E0,eol,size:%(size)d" % faces)


    def OnUpdateUI(self, evt):
        braces = self.GetMatchingBraces()
        
        # check for matching braces
        braceAtCaret = -1
        braceOpposite = -1
        charBefore = None
        caretPos = self.GetCurrentPos()
        if caretPos > 0:
            charBefore = self.GetCharAt(caretPos - 1)
            styleBefore = self.GetStyleAt(caretPos - 1)

        # check before
        if charBefore and chr(charBefore) in braces and styleBefore == wx.stc.STC_P_OPERATOR:
            braceAtCaret = caretPos - 1

        # check after
        if braceAtCaret < 0:
            charAfter = self.GetCharAt(caretPos)
            styleAfter = self.GetStyleAt(caretPos)
            if charAfter and chr(charAfter) in braces and styleAfter == wx.stc.STC_P_OPERATOR:
                braceAtCaret = caretPos

        if braceAtCaret >= 0:
            braceOpposite = self.BraceMatch(braceAtCaret)

        if braceAtCaret != -1  and braceOpposite == -1:
            self.BraceBadLight(braceAtCaret)
        else:
            self.BraceHighlight(braceAtCaret, braceOpposite)

        evt.Skip()


    def DoIndent(self):
        (text, caretPos) = self.GetCurLine()

        self._tokenizerChars = {}  # This is really too much, need to find something more like a C array
        for i in range(len(text)):
            self._tokenizerChars[i] = 0
        ctext = StringIO.StringIO(text)
        try:
            tokenize.tokenize(ctext.readline, self)
        except:
            pass

        # Left in for debugging purposes:
        #for i in range(len(text)):
        #    print i, text[i], self._tokenizerChars[i]

        if caretPos == 0 or len(string.strip(text)) == 0:  # At beginning of line or within an empty line
            self.AddText('\n')
        else:
            doExtraIndent = False
            brackets = False
            commentStart = -1
            if caretPos > 1:
                startParenCount = 0
                endParenCount = 0
                startSquareBracketCount = 0
                endSquareBracketCount = 0
                startCurlyBracketCount = 0
                endCurlyBracketCount = 0
                startQuoteCount = 0
                endQuoteCount = 0
                for i in range(caretPos - 1, -1, -1): # Go through each character before the caret
                    if i >= len(text): # Sometimes the caret is at the end of the text if there is no LF
                        continue
                    if self._tokenizerChars[i] == 1:
                        continue
                    elif self._tokenizerChars[i] == 2:
                        startQuoteCount = startQuoteCount + 1
                    elif self._tokenizerChars[i] == 3:
                        endQuoteCount = endQuoteCount + 1
                    elif text[i] == '(': # Would be nice to use a dict for this, but the code is much more readable this way
                        startParenCount = startParenCount + 1
                    elif text[i] == ')':
                        endParenCount = endParenCount + 1
                    elif text[i] == "[":
                        startSquareBracketCount = startSquareBracketCount + 1
                    elif text[i] == "]":
                        endSquareBracketCount = endSquareBracketCount + 1
                    elif text[i] == "{":
                        startCurlyBracketCount = startCurlyBracketCount + 1
                    elif text[i] == "}":
                        endCurlyBracketCount = endCurlyBracketCount + 1
                    elif text[i] == "#":
                        commentStart = i
                        break
                    if startQuoteCount > endQuoteCount or startParenCount > endParenCount or startSquareBracketCount > endSquareBracketCount or startCurlyBracketCount > endCurlyBracketCount:
                        if i + 1 >= caretPos:  # Caret is right at the open paren, so just do indent as if colon was there
                            doExtraIndent = True
                            break
                        else:
                            spaces = " " * (i + 1)
                            brackets = True
                            break
            if not brackets:
                spaces = text[0:len(text) - len(string.lstrip(text))]
                if caretPos < len(spaces):  # If within the opening spaces of a line
                    spaces = spaces[:caretPos]

                # strip comment off
                if commentStart != -1:
                    text = text[0:commentStart]

                textNoTrailingSpaces = text[0:caretPos].rstrip()
                if doExtraIndent or len(textNoTrailingSpaces) and textNoTrailingSpaces[-1] == ':':
                    spaces = spaces + ' ' * self.GetIndent()
            self.AddText('\n' + spaces)
        self.EnsureCaretVisible()


    # Callback for tokenizer in self.DoIndent
    def __call__(self, toktype, toktext, (srow,scol), (erow,ecol), line):
        if toktype == tokenize.COMMENT:
            for i in range(scol, ecol + 1):
                self._validChars[i] = False
        elif toktype == token.STRING:
            self._tokenizerChars[scol] = 2 # Open quote
            self._tokenizerChars[ecol - 1] = 3 # Close quote
            for i in range(scol + 1, ecol - 2):
                self._tokenizerChars[i] = 1 # Part of string, 1 == ignore the char
                
    def IsImportType(self,start_pos):
        line_start_pos = self.PositionFromLine(self.LineFromPosition(start_pos))
        at = self.GetCharAt(start_pos)
        while chr(at) == self.TYPE_BLANK_WORD:
            start_pos -= 1
            at = self.GetCharAt(start_pos)
        if start_pos <= line_start_pos:
            return False
        word = self.GetTypeWord(start_pos)
        return True if word == self.TYPE_IMPORT_WORD else False
        
    def IsFromType(self,start_pos):
        line_start_pos = self.PositionFromLine(self.LineFromPosition(start_pos))
        at = self.GetCharAt(start_pos)
        while chr(at) == self.TYPE_BLANK_WORD:
            start_pos -= 1
            at = self.GetCharAt(start_pos)
        if start_pos <= line_start_pos:
            return False
        word = self.GetTypeWord(start_pos)
        return True if word == self.TYPE_FROM_WORD else False
        
    def IsFromModuleType(self,start_pos):
        line_start_pos = self.PositionFromLine(self.LineFromPosition(start_pos))
        at = self.GetCharAt(start_pos)
        while chr(at) == self.TYPE_BLANK_WORD:
            start_pos -= 1
            at = self.GetCharAt(start_pos)
        if start_pos <= line_start_pos:
            return False
        word = self.GetTypeWord(start_pos)
        start_pos -= len(word)
        start_pos -= 1
        at = self.GetCharAt(start_pos)
        while chr(at) == self.TYPE_BLANK_WORD:
            start_pos -= 1
            at = self.GetCharAt(start_pos)
        if start_pos <= line_start_pos:
            return False
        word = self.GetTypeWord(start_pos)
        return True if word == self.TYPE_FROM_WORD else False

    def IsFromImportType(self,start_pos):
        line_start_pos = self.PositionFromLine(self.LineFromPosition(start_pos))
        at = self.GetCharAt(start_pos)
        while chr(at) == self.TYPE_BLANK_WORD:
            start_pos -= 1
            at = self.GetCharAt(start_pos)
        if start_pos <= line_start_pos:
            return False,''
        word = self.GetTypeWord(start_pos)
        if word == self.TYPE_IMPORT_WORD:
            start_pos -= len(self.TYPE_IMPORT_WORD)
            start_pos -= 1
            at = self.GetCharAt(start_pos)
            while chr(at) == self.TYPE_BLANK_WORD:
                start_pos -= 1
                at = self.GetCharAt(start_pos)
            if start_pos <= line_start_pos:
                return False,''
            from_word = self.GetTypeWord(start_pos)
            start_pos -= len(from_word)
            start_pos -= 1
            at = self.GetCharAt(start_pos)
            while chr(at) == self.TYPE_BLANK_WORD:
                start_pos -= 1
                at = self.GetCharAt(start_pos)
            if start_pos <= line_start_pos:
                return False,''
            word = self.GetTypeWord(start_pos)
            return True if word == self.TYPE_FROM_WORD else False,from_word
        return False,''
                
    def OnChar(self,event):
        if self.CallTipActive():
            self.CallTipCancel()
        key = event.GetKeyCode()
        pos = self.GetCurrentPos()
        # Tips
        if key == ord("("):
            self.AddText("(")
            self.GetArgTip(pos)
        elif key == ord(self.TYPE_POINT_WORD):
            self.AddText(self.TYPE_POINT_WORD)
            self.ListMembers(pos)
        elif key == ord(self.TYPE_BLANK_WORD):
            self.AddText(self.TYPE_BLANK_WORD)
            is_from_import_type,name = self.IsFromImportType(pos)
            if is_from_import_type:
                member_list = intellisence.IntellisenceManager().GetMemberList(name)
                if member_list == []:
                    return
                member_list.insert(0,"*")
                self.AutoCompShow(0, string.join(member_list))
            elif self.IsImportType(pos) or self.IsFromType(pos):
                import_list = intellisence.IntellisenceManager().GetImportList()
                if import_list == []:
                    return
                self.AutoCompShow(0, string.join(import_list))
            elif self.IsFromModuleType(pos):
                self.AutoCompShow(0, string.join([self.TYPE_IMPORT_WORD]))
        else:
            event.Skip()
            
    def GetArgTip(self,pos):
        text = self.GetTypeWord(pos)
        line = self.LineFromPosition(pos)
        module_scope = wx.GetApp().GetDocumentManager().GetCurrentView().ModuleScope
        if module_scope is None:
            return
        scope = module_scope.FindScope(line+1)
        scope_found = scope.FindDefinitionScope(text)
        tip = ''
        if None != scope_found:
            if scope_found.Parent is not None and isinstance(scope_found.Node,nodeast.ImportNode):
                tip = scope_found.GetImportMemberArgTip(text)
            else:
                tip = scope_found.GetArgTip()
        if tip == '':
            return
        self.CallTipSetBackground("yellow")
        self.CallTipShow(pos,tip)    

    def IsListMemberFlag(self,pos):
        at = self.GetCharAt(pos)
        if chr(at) != self.TYPE_POINT_WORD:
            return False
        return True

    def ListMembers(self,pos):
        text = self.GetTypeWord(pos)
        line = self.LineFromPosition(pos)
        module_scope = wx.GetApp().GetDocumentManager().GetCurrentView().ModuleScope
        if module_scope is None:
            return
        scope = module_scope.FindScope(line+1)
        scope_found = scope.FindDefinitionScope(text)
        member_list = []
        if None != scope_found:
            if scope_found.Parent is not None and isinstance(scope_found.Node,nodeast.ImportNode):
                member_list = scope_found.GetImportMemberList(text)
            else:
                if scope.IsClassMethodScope() and scope.Parent == scope_found:
                    member_list = scope_found.GetClassMemberList()
                else:
                    member_list = scope_found.GetMemberList()
        if member_list == []:
            return
        self.AutoCompSetIgnoreCase(True)
        self.AutoCompShow(0, string.join(member_list))

    def IsCaretLocateInWord(self,pos=-1):
        if pos == -1:
            pos = self.GetCurrentPos()
        line = self.LineFromPosition(pos)
        line_text = self.GetLine(line).strip()
        if line_text == "":
            return False
        if line_text[0] == '#':
            return False
        start_pos = self.WordStartPosition(pos,True)
        end_pos = self.WordEndPosition(pos,True)
        word = self.GetTextRange(start_pos,end_pos).strip()
        return False if word == "" else True

    def GotoDefinition(self):
        line = self.GetCurrentLine()
        pos = self.GetCurrentPos()
        text = self.GetTypeWord(pos)
        open_new_doc = False
        module_scope = Service.Service.GetActiveView().ModuleScope
        if module_scope is None:
            scope_found = None
        else:
            scope = module_scope.FindScope(line)
            scope_found = scope.FindDefinitionMember(text)
        if scope_found is None:
            wx.MessageBox(_("Cannot find definition") + "\"" + text + "\"",_("Goto Definition"),wx.OK|wx.ICON_EXCLAMATION,wx.GetApp().GetTopWindow())
        else:
            if scope_found.Parent is None:
                wx.GetApp().GotoView(scope_found.Module.Path,0)
            else:
                open_new_doc = (scope_found.Root != scope.Root)
                if not open_new_doc:
                    doc_view = wx.GetApp().GetDocumentManager().GetCurrentView()
                    startPos = doc_view.PositionFromLine(scope_found.Node.Line)
                    doc_view.GotoPos(startPos + scope_found.Node.Col)
                else:
                    if -1 == scope_found.Node.Line:
                        wx.MessageBox(_("Cannot go to definition") + "\"" + text + "\"",_("Goto Definition"),wx.OK|wx.ICON_EXCLAMATION,wx.GetApp().GetTopWindow())
                        return
                    wx.GetApp().GotoViewPos(scope_found.Root.Module.Path,scope_found.Node.Line,scope_found.Node.Col)


    def OnDwellStart(self, evt):
        mpoint = wx.GetMousePosition()
        brect = self.GetScreenRect()
        #avoid trigger tool many times
        if not brect.Contains(mpoint) or \
           not self.IsShown() or \
           not wx.GetApp().GetTopWindow().IsActive():
            return
        position = evt.Position
        if position >= 0 and self.IsCaretLocateInWord(position):
            line = self.LineFromPosition(position) + 1
            dwellword = self.GetTypeWord(position)
            doc_view = Service.Service.GetActiveView()
            if doc_view.GetLangLexer() == parserconfig.LANG_PYTHON_LEXER:
                module_scope = doc_view.ModuleScope
                if module_scope is None:
                    scope_found = None
                else:
                    scope = module_scope.FindScope(line)
                    scope_found = scope.FindDefinitionMember(dwellword)
                if scope_found is not None:
                    doc = scope_found.GetDoc()
                    if doc is not None:
                        self.CallTipShow(position, doc.decode('utf-8'))
            else:
                app_debugLogger.debug('active view is not python code view')
        
        CodeEditor.CodeCtrl.OnDwellStart(self,evt)

    def OnDwellEnd(self, evt):
        self.CallTipCancel()
        CodeEditor.CodeCtrl.OnDwellEnd(self,evt)

class PythonOptionsPanel(wx.Panel):

    def __init__(self, parent, id):
        wx.Panel.__init__(self, parent, id)
        pathLabel = wx.StaticText(self, -1, _("Interpreters:"))
        config = wx.ConfigBase_Get()
      ###  path = config.Read("ActiveGridPythonLocation")
        choices,default_selection = Interpreter.InterpreterManager().GetChoices()
        self._pathTextCtrl = wx.ComboBox(self, -1,choices=choices, style = wx.CB_READONLY)
        if len(choices) > 0:
            self._pathTextCtrl.SetSelection(default_selection)
       ## self._pathTextCtrl.SetToolTipString(self._pathTextCtrl.GetValue())
        ##self._pathTextCtrl.SetInsertionPointEnd()
        choosePathButton = wx.Button(self, -1, _("Configure..."))
        pathSizer = wx.BoxSizer(wx.HORIZONTAL)
        HALF_SPACE = 5
        SPACE = 10
        pathSizer.Add(pathLabel, 0, wx.ALIGN_CENTER_VERTICAL|wx.LEFT|wx.TOP, HALF_SPACE)
        pathSizer.Add(self._pathTextCtrl, 1, wx.EXPAND|wx.LEFT|wx.TOP, HALF_SPACE)
        pathSizer.Add(choosePathButton, 0, wx.ALIGN_RIGHT|wx.LEFT|wx.RIGHT|wx.TOP, HALF_SPACE)
        wx.EVT_BUTTON(self, choosePathButton.GetId(), self.OnChoosePath)
        mainSizer = wx.BoxSizer(wx.VERTICAL)                
        mainSizer.Add(pathSizer, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, SPACE)

        self._otherOptions = STCTextEditor.TextOptionsPanel(self, -1, configPrefix = "Python", label = "Python", hasWordWrap = True, hasTabs = True, addPage=False, hasFolding=True)
        mainSizer.Add(self._otherOptions, 0, wx.EXPAND|wx.BOTTOM, SPACE)
        self.SetSizer(mainSizer)
        parent.AddPage(self, _("Python"))
        
    def OnChoosePath(self, event):
        dlg = InterpreterConfigDialog.InterpreterConfigDialog(self,-1,_("Configure Interpreter"))
        dlg.CenterOnParent()
        status = dlg.ShowModal()
        dlg.Destroy()
        choices,default_selection = Interpreter.InterpreterManager().GetChoices()
        self._pathTextCtrl.Clear()
        if len(choices) > 0:
            self._pathTextCtrl.InsertItems(choices,0)
            self._pathTextCtrl.SetSelection(default_selection)
            wx.GetApp().AddInterpreters()
        if status == wx.ID_OK:
            Interpreter.InterpreterManager().SavePythonInterpretersConfig()

    def OnOK(self, optionsDialog):
        config = wx.ConfigBase_Get()
        self._otherOptions.OnOK(optionsDialog)
        Interpreter.InterpreterManager().SavePythonInterpretersConfig()
        

    def GetIcon(self):
        return getPythonIcon()
        

#----------------------------------------------------------------------------
# Icon Bitmaps - generated by encode_bitmaps.py
#----------------------------------------------------------------------------
from wx import ImageFromStream, BitmapFromImage
import cStringIO


def getPythonData():
    return \
'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\
\x00\x00\x00\x1f\xf3\xffa\x00\x00\x00\x04sBIT\x08\x08\x08\x08|\x08d\x88\x00\
\x00\x01\xe7IDAT8\x8d}\x921h\x13Q\x18\xc7\x7fw\xb9\x0ei\x9d*\xbd\xeb\x10\x8f\
,\x99\x1c*A[\xaa\x19B\xe8\xd0\xb1\x0e%K\x87\x88T2\x88Cqp\tD\x14i\xe9\xe0V\
\xdaQ\xb7\xe0P\xa1\x8b\xa0(\x95$z\xd5Q1\x90\xa2\xd7\x9a4^\x87\xa0`\x92!w9\
\x87\xf8.\xb9\xa6\xc97\xbd\xef{\xef\xfb\xbd\xff\xfb\xbfO*~;v\xf9\x1f\xad\xba\
\x05@\xf9\xd4\x06\xc0::$\xbb\x96\x92\x18\x11\n@(4\xdd\xcdB\xd3\xd4\x1d\x85\
\x8b\x97\xe1\xe3;\x83\x99\xe5\x15\xb2\xe0\x8e\x82\xc8\xa3\xe8\x003\xcb+\xac\
\xaee\xdda\xfb\xb2\x90\rPw\x14\x00\x9a\xb5\n\xbf\xfflSz\x9d\xa2Y\xdc"zca\xe8\
\x05\xb2h\x14\xcd\xd0\xf3B\x9f\x98\xe5\xf9\xde\x13"\xaaB\xc7\xb1\xcfU!\x0b\
\xc3D4k\x15\xac\x93\x03\xf4\x89Y\xaf\x96\xffT\x028\x17\xa2\xf4\'\xcdZ\x85\
\xf7F\x06{\xaa\x80ev\xc1\x91\xb91>\x18\x0f\xb8\xb7\x95a\xe9\xca\x0b:\x8e\xed\
\xca\x01E\x1a\x00\x98\r\x89\x92\x91\xa1\xda\xd8\x87\x06ha\x1f\x1b\x80\xcd\
\x9d%\xe0\xa5\x0f"[G\x87\x98\x8d\xde/ia\x05-\xac`\x996\xf9\\\x0b\xcb\xb4)\
\x1bmOMn\xf7\xd5\xf0\'\\\x8b\xdces\xe7\x8d\xef\x80h\xd6\xc2\n\xf9\\\x0b]\xf5\
\xab\xf2\xcdApR#\xf1kp4b\xc9 \xf9\\\x0b\x80\xe4\xcdE\xaf\xdeqlW\xaeVL\xaf`~\
\xd9\x03@W\xd3\x00\xc4\x13\x0b\xc4\x92A\xcf\xd0\xf9\xe8:\x89\xebW\x01(|\xfd\
\xe1\xbe-~F\xbas\xff\x91\xf75\x82n\x9d\x1c\xf0}\xfciw\xdd\xe7A<\xd1\x1b\xa8j\
c\x9f\xb2\xd1F\x92\xe4\x80O\x12\xc0\xc6\xb3\x14\xf6Ta\xe0)g\x81\xba\x9a\xf6\
\x9b(\x07\x14I@\x84lq\xb8?\xe6\xa3\xeb\x00\xdc\xba\x9d\xf4+\x10*~\xfem\xf3\
\xf8\xe1\x06\xc7\xa7\xdb\xe8j\x9a\xf8\xdc\xa4\xb7\x1f[\\\xe5\xd2\x851/\xff\
\x07\xac\x9b\xd1e\x12\x96\x0f\xfd\x00\x00\x00\x00IEND\xaeB`\x82' 


def getPythonBitmap():
    return BitmapFromImage(getPythonImage())

def getPythonImage():
    stream = cStringIO.StringIO(getPythonData())
    return ImageFromStream(stream)

def getPythonIcon():
    return wx.IconFromBitmap(getPythonBitmap())
