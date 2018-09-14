#----------------------------------------------------------------------------
# Name:         STCTextEditor.py
# Purpose:      Text Editor for wx.lib.pydocview tbat uses the Styled Text Control
#
# Author:       Peter Yared, Morgan Hua
#
# Created:      8/10/03
# CVS-ID:       $Id$
# Copyright:    (c) 2003-2006 ActiveGrid, Inc.
# License:      wxWindows License
#----------------------------------------------------------------------------

import wx
import wx.stc
import wx.lib.docview
import wx.lib.multisash
import string
import FindService
import os
import sys
import chardet
import codecs
import shutil
import FileObserver
import WxThreadSafe
import noval.tool.syntax.lang as lang
import MarkerService
import TextService
import CompletionService
import NavigationService
import consts
import noval.util.sysutils as sysutilslib
import noval.util.fileutils as fileutils
import noval.parser.utils as parserutils
import FindTextCtrl
from noval.tool.syntax import syntax
import noval.util.strutils as strutils
import json
import noval.util.utils as utils
import EOLFormat

_ = wx.GetTranslation

#----------------------------------------------------------------------------
# Classes
#----------------------------------------------------------------------------

class TextDocument(wx.lib.docview.Document):
    
    ASC_FILE_ENCODING = "ascii"
    UTF_8_FILE_ENCODING = "utf-8"
    ANSI_FILE_ENCODING = "cp936"
    
    DEFAULT_FILE_ENCODING = ASC_FILE_ENCODING
    
    def __init__(self):
        wx.lib.docview.Document .__init__(self)
        self._inModify = False
        self.file_watcher = FileObserver.FileAlarmWatcher()
        self._is_watched = False
        self.file_encoding =  wx.ConfigBase_Get().Read(consts.DEFAULT_FILE_ENCODING_KEY,TextDocument.DEFAULT_FILE_ENCODING)
        if self.file_encoding == "":
            self.file_encoding = TextDocument.DEFAULT_FILE_ENCODING
        self._is_new_doc = True

    def GetSaveObject(self,filename):
        return codecs.open(filename, 'w',self.file_encoding)

    def DoSaveBefore(self):
        if self._is_watched:
            self.file_watcher.StopWatchFile(self)
        #should check document data encoding first before save document
        self.file_encoding = self.DetectDocumentEncoding()
    
    def DoSaveBehind(self):
        pass

    def GetOpenDocument(self,filepath):
        if parserutils.ComparePath(self.GetFilename(),filepath):
            return None
        openDocs =  wx.GetApp().GetDocumentManager().GetDocuments()[:]  # need copy or docs shift when closed
        for d in openDocs:
            if parserutils.ComparePath(d.GetFilename(),filepath):
                return d
        return None
        
    def SaveAs(self):
        """
        Prompts the user for a file to save to, and then calls OnSaveDocument.
        """
        docTemplate = self.GetDocumentTemplate()
        if not docTemplate:
            return False

        descr = _(docTemplate.GetDescription()) + " (" + docTemplate.GetFileFilter() + ") |" + docTemplate.GetFileFilter()  # spacing is important, make sure there is no space after the "|", it causes a bug on wx_gtk
        if docTemplate.GetDocumentType() == TextDocument and docTemplate.GetFileFilter() != "*.*":
            default_ext = ""
            descr = _("Any File") +  "(*.*) |*.*|%s" % descr
        else:
            default_ext = docTemplate.GetDefaultExtension()
        filename = wx.FileSelector(_("Save As"),
                                   docTemplate.GetDirectory(),
                                   wx.lib.docview.FileNameFromPath(self.GetFilename()),
                                   default_ext,
                                   wildcard = descr,
                                   flags = wx.SAVE | wx.OVERWRITE_PROMPT,
                                   parent = self.GetDocumentWindow())
        if filename == "":
            return False

        #name, ext = os.path.splitext(filename)
        #if ext == "":
         #   filename += '.' + docTemplate.GetDefaultExtension()
            
        if self.GetOpenDocument(filename):
            wx.MessageBox(_("File has already been opened,could not overwrite it."),wx.GetApp().GetAppName(),wx.OK | wx.ICON_WARNING,
                                  self.GetDocumentWindow())
            return False
            
        if not self.OnSaveDocument(filename):
            return False

        self.SetFilename(filename)
        self.SetTitle(wx.lib.docview.FileNameFromPath(filename))

        for view in self._documentViews:
            view.OnChangeFilename()

        if docTemplate.FileMatchesTemplate(filename):
            self.GetDocumentManager().AddFileToHistory(filename)
            
        return True
        
    def OnSaveDocument(self, filename):
        """
        Constructs an output file for the given filename (which must
        not be empty), and calls SaveObject. If SaveObject returns true, the
        document is set to unmodified; otherwise, an error message box is
        displayed.
        """
        if not filename:
            return False

        msgTitle = wx.GetApp().GetAppName()
        if not msgTitle:
            msgTitle = _("File Error")

        backupFilename = None
        fileObject = None
        copied = False
        try:
            self.DoSaveBefore()
            # if current file exists, move it to a safe place temporarily
            if os.path.exists(filename):

                # Check if read-only.
                if not os.access(filename, os.W_OK):
                    wx.MessageBox(_("Could not save '%s':  No write permission to overwrite existing file.") % \
                                  wx.lib.docview.FileNameFromPath(filename),
                                  msgTitle,
                                  wx.OK | wx.ICON_EXCLAMATION,
                                  self.GetDocumentWindow())
                    return False

                backupFilename = "%s.bk%s" % (filename, 1)
                shutil.copy(filename, backupFilename)
                copied = True
            fileObject = self.GetSaveObject(filename)
            self.SaveObject(fileObject)
            fileObject.close()
            fileObject = None
            
            if backupFilename:
                os.remove(backupFilename)
        except:
            # for debugging purposes
          ##  import traceback
            ##traceback.print_exc()

            if fileObject:
                fileObject.close()  # file is still open, close it, need to do this before removal 

            # save failed, remove copied file
            if backupFilename and copied:
                shutil.copy(backupFilename,filename)
                os.remove(backupFilename)

            wx.MessageBox(_("Could not save '%s':  %s") % (wx.lib.docview.FileNameFromPath(filename), sys.exc_value),
                          msgTitle,
                          wx.OK | wx.ICON_ERROR,
                          self.GetDocumentWindow())
                          
            if not self._is_new_doc:
                self.SetDocumentModificationDate()
            return False

        self.SetFilename(filename, True)
        self.Modify(False)
        self.SetDocumentSaved(True)
        self._is_watched = True
        self._is_new_doc = False
        self.file_watcher.StartWatchFile(self)
        self.DoSaveBehind()
        self.SetDocumentModificationDate()
        #if wx.Platform == '__WXMAC__':  # Not yet implemented in wxPython
        #    wx.FileName(file).MacSetDefaultTypeAndCreator()
        return True

    def DetectFileEncoding(self,filepath):

        file_encoding = TextDocument.DEFAULT_FILE_ENCODING
        try:
            with open(filepath,"rb") as f:
                data = f.read()
                result = fileutils.detect(data)
                file_encoding = result['encoding']
        except:
            pass
        #if detect file encoding is None,we should assume the file encoding is ansi,which cp936 encoding is instead
        if None == file_encoding or file_encoding.lower().find('iso') != -1:
            file_encoding = TextDocument.ANSI_FILE_ENCODING
        return file_encoding
        
    def DetectDocumentEncoding(self):
        view = self.GetFirstView()
        file_encoding = self.file_encoding
        #when the file encoding is accii or new document,we should check the document data contain chinese character,
        #the we should change the document encoding to utf-8 to save chinese character
        if file_encoding == self.ASC_FILE_ENCODING or self.IsNewDocument:
            guess_encoding = file_encoding.lower()
            if guess_encoding == self.ASC_FILE_ENCODING:
                guess_encoding = self.UTF_8_FILE_ENCODING
            result = fileutils.detect(view.GetValue().encode(guess_encoding))
            file_encoding = result['encoding']
            if None == file_encoding:
                file_encoding = TextDocument.ASC_FILE_ENCODING
        return file_encoding

    def OnOpenDocument(self, filename):
        """
        Constructs an input file for the given filename (which must not
        be empty), and calls LoadObject. If LoadObject returns true, the
        document is set to unmodified; otherwise, an error message box is
        displayed. The document's views are notified that the filename has
        changed, to give windows an opportunity to update their titles. All of
        the document's views are then updated.
        """
        if not self.OnSaveModified():
            return False

        msgTitle = wx.GetApp().GetAppName()
        if not msgTitle:
            msgTitle = _("File Error")
        self.file_encoding = self.DetectFileEncoding(filename)
        fileObject = None
        try:
            if self.file_encoding == 'binary':
                fileObject = open(filename, 'rb')
                is_bytes = True
            else:
                fileObject = codecs.open(filename, 'r',self.file_encoding)
                is_bytes = False
            self.LoadObject(fileObject,is_bytes)
            fileObject.close()
            fileObject = None
        except:
            # for debugging purposes
            #import traceback
            #traceback.print_exc()

            if fileObject:
                fileObject.close()  # file is still open, close it 

            wx.MessageBox(_("Could not open '%s':  %s") % (wx.lib.docview.FileNameFromPath(filename), sys.exc_value),
                          msgTitle,
                          wx.OK | wx.ICON_ERROR,
                          self.GetDocumentWindow())
            return False

        self.SetDocumentModificationDate()
        self.SetFilename(filename, True)
        self.Modify(False)
        self.SetDocumentSaved(True)
        self.UpdateAllViews()
        self.file_watcher.AddFileDoc(self)
        self._is_watched = True
        self._is_new_doc = False
        rember_file_pos = wx.ConfigBase_Get().ReadInt(consts.REMBER_FILE_KEY, True)
        if rember_file_pos:
            pos = NavigationService.NavigationService.DocMgr.GetPos(filename)
            self.GetFirstView().GetCtrl().GotoPos(pos)
        self.GetFirstView().GetCtrl().ScrollToColumn(0)
        self.GetFirstView().OnUpdateStatusBar(None)
        return True

    @property
    def IsWatched(self):
        return self._is_watched

    @property
    def FileWatcher(self):
        return self.file_watcher

    def SaveObject(self, fileObject):
        view = self.GetFirstView()
        fileObject.write(view.GetValue())
        view.SetModifyFalse()
        return True
        
    def LoadObject(self, fileObject,is_bytes=False):
        view = self.GetFirstView()
        data = fileObject.read()
        if is_bytes:
            view.SetBinaryValue(data)
        else:
            view.SetValue(data)
        view.SetModifyFalse()
        return True

    def IsModified(self):
        filename = self.GetFilename()
        if filename and not os.path.exists(filename) and not self._is_new_doc:
            return True
        view = self.GetFirstView()
        if view:
            return view.IsModified()
        return False
    
    @property
    def IsNewDocument(self):
        return self._is_new_doc

    def Modify(self, modify):
        if self._inModify:
            return
        self._inModify = True
        view = self.GetFirstView()
        if not modify and view:
            view.SetModifyFalse()
        wx.lib.docview.Document.Modify(self, modify)  # this must called be after the SetModifyFalse call above.
        self._inModify = False
        
    def OnCreateCommandProcessor(self):
        # Don't create a command processor, it has its own
        pass

# Use this to override MultiClient.Select to prevent yellow background.  
def MultiClientSelectBGNotYellow(a):     
    a.GetParent().multiView.UnSelect()   
    a.selected = True    
    #a.SetBackgroundColour(wx.Colour(255,255,0)) # Yellow        
    a.Refresh()

class TextView(wx.lib.docview.View):
    #book marker margin index
    BOOK_MARKER_NUM = 0
    BOOK_MARGIN_WIDTH = 12
    BOOK_MARKER_MASK = 0x1
    #line marker margin index
    LINE_MARKER_NUM = 1
    #fold marker margin index
    FOLD_MARKER_NUM = 2
    FOLD_MARGIN_WIDTH = 12
    
    #----------------------------------------------------------------------------
    # Overridden methods
    #----------------------------------------------------------------------------

    def __init__(self):
        wx.lib.docview.View.__init__(self)
        self._textEditor = None
        self._markerCount = 0
        self._commandProcessor = None
        self._dynSash = None
        self._is_alarming = False
        self._alarm_type = -1
        # Initialize the classes position manager for the first control
        # that is created only.
        if not NavigationService.NavigationService.DocMgr.IsInitialized():
            NavigationService.NavigationService.DocMgr.InitPositionCache()


    def GetCtrlClass(self):
        """ Used in split window to instantiate new instances """
        return TextCtrl

    def GetType(self):
        return consts.TEXT_VIEW
    
    def GetLangId(self):
        return lang.ID_LANG_TXT

    def GetCtrl(self):
        if wx.Platform == "__WXMAC__":
            # look for active one first  
            self._textEditor = self._GetActiveCtrl(self._dynSash)        
            if self._textEditor == None:  # it is possible none are active       
                # look for any existing one      
                self._textEditor = self._FindCtrl(self._dynSash)
        return self._textEditor


    def SetCtrl(self, ctrl):
        self._textEditor = ctrl
                

    def OnCreatePrintout(self):
        """ for Print Preview and Print """
        return TextPrintout(self, self.GetDocument().GetPrintableName())

            
    def OnCreate(self, doc, flags):
        frame = wx.GetApp().CreateDocumentFrame(self, doc, flags, style = wx.DEFAULT_FRAME_STYLE | wx.NO_FULL_REPAINT_ON_RESIZE)
        # wxBug: DynamicSashWindow doesn't work on Mac, so revert to
        # multisash implementation
        if wx.Platform == "__WXMAC__":
            wx.lib.multisash.MultiClient.Select = MultiClientSelectBGNotYellow
            self._dynSash = wx.lib.multisash.MultiSash(frame, -1)
            self._dynSash.SetDefaultChildClass(self.GetCtrlClass()) # wxBug:  MultiSash instantiates the first TextCtrl with this call
            
            self._textEditor = self.GetCtrl()  # wxBug: grab the TextCtrl from the MultiSash datastructure
        else:
            self._dynSash = wx.gizmos.DynamicSashWindow(frame, -1, style=wx.CLIP_CHILDREN)
            self._dynSash._view = self
            self._textEditor = self.GetCtrlClass()(self._dynSash, -1, style=wx.NO_BORDER)
        wx.EVT_LEFT_DOWN(self._textEditor, self.OnLeftClick)
        self._textEditor.Bind(wx.stc.EVT_STC_MODIFIED, self.OnModify)
        
        self._CreateSizer(frame)
        self.Activate()
        frame.Show(True)
        frame.Layout()
        return True


    def OnModify(self, event):
        self.GetDocument().Modify(self._textEditor.GetModify())
        

    def _CreateSizer(self, frame):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self._dynSash, 1, wx.EXPAND)
        frame.SetSizer(sizer)


    def OnLeftClick(self, event):
        self.Activate()
        event.Skip()


    def OnUpdate(self, sender = None, hint = None):
        if wx.lib.docview.View.OnUpdate(self, sender, hint):
            return

        if hint == "ViewStuff":
            self.GetCtrl().SetViewDefaults()
        elif hint == "Font":
            font, color = self.GetCtrl().GetFontAndColorFromConfig()
            self.GetCtrl().SetFont(font)
            self.GetCtrl().SetFontColor(color)
            
    def OnActivateView(self, activate, activeView, deactiveView):
        if activate and self.GetCtrl():
            if isinstance(deactiveView,TextView):
                text_ctrl = deactiveView.GetCtrl()
                if text_ctrl and text_ctrl.AutoCompActive():
                    text_ctrl.AutoCompCancel()
            # In MDI mode just calling set focus doesn't work and in SDI mode using CallAfter causes an endless loop
            if self.GetDocumentManager().GetFlags() & wx.lib.docview.DOC_SDI:
                self.SetFocus()
            else:
                wx.CallAfter(self.SetFocus)

    def SetFocus(self):
        if self.GetCtrl():
            self.GetCtrl().SetFocus()           
                                
    def OnClose(self, deleteWindow = True):
        if not wx.lib.docview.View.OnClose(self, deleteWindow):
            return False
    
        document = self.GetDocument()
        if document.IsWatched:
            document.FileWatcher.RemoveFileDoc(document)
        if not document.IsNewDocument:
            NavigationService.NavigationService.DocMgr.AddRecord([document.GetFilename(),
                                           self.GetCtrl().GetCurrentPos()])
        self.Activate(False)
        if deleteWindow and self.GetFrame():
            self.GetFrame().Destroy()

        return True


    def ProcessEvent(self, event):        
        id = event.GetId()
        if id == wx.ID_UNDO:
            self.GetCtrl().Undo()
            return True
        elif id == wx.ID_REDO:
            self.GetCtrl().Redo()
            return True
        elif id == wx.ID_CUT:
            self.GetCtrl().Cut()
            return True
        elif id == wx.ID_COPY:
            self.GetCtrl().Copy()
            return True
        elif id == wx.ID_PASTE:
            self.GetCtrl().OnPaste()
            return True
        elif id == wx.ID_CLEAR:
            self.GetCtrl().OnClear()
            return True
        elif id == wx.ID_SELECTALL:
            self.GetCtrl().SelectAll()
            return True
        elif id == TextService.VIEW_WHITESPACE_ID:
            self.GetCtrl().SetViewWhiteSpace(not self.GetCtrl().GetViewWhiteSpace())
            return True
        elif id == TextService.VIEW_EOL_ID:
            self.GetCtrl().SetViewEOL(not self.GetCtrl().GetViewEOL())
            return True
        elif id == TextService.VIEW_INDENTATION_GUIDES_ID:
            self.GetCtrl().SetIndentationGuides(not self.GetCtrl().GetIndentationGuides())
            return True
        elif id == TextService.VIEW_RIGHT_EDGE_ID:
            self.GetCtrl().SetViewRightEdge(not self.GetCtrl().GetViewRightEdge())
            return True
        elif id == TextService.VIEW_LINE_NUMBERS_ID:
            self.GetCtrl().SetViewLineNumbers(not self.GetCtrl().GetViewLineNumbers())
            return True
        elif id == TextService.ZOOM_NORMAL_ID:
            self.GetCtrl().SetZoom(0)
            return True
        elif id == TextService.ZOOM_IN_ID:
            self.GetCtrl().CmdKeyExecute(wx.stc.STC_CMD_ZOOMIN)
            return True
        elif id == TextService.ZOOM_OUT_ID:
            self.GetCtrl().CmdKeyExecute(wx.stc.STC_CMD_ZOOMOUT)
            return True
        elif id == TextService.CHOOSE_FONT_ID:
            self.OnChooseFont()
            return True
        elif id == TextService.WORD_WRAP_ID:
            self.GetCtrl().SetWordWrap(not self.GetCtrl().GetWordWrap())
            return True
        elif id == FindService.FindService.FIND_ID:
            self.OnFind()
            return True
        elif id == FindService.FindService.FIND_PREVIOUS_ID:
            self.DoFindText(forceFindPrevious = True)
            return True
        elif id == FindService.FindService.FIND_NEXT_ID:
            self.DoFindText(forceFindNext = True)
            return True
        elif id == FindService.FindService.REPLACE_ID:
            self.OnFind(replace = True)
            return True
        elif id == FindService.FindService.FINDONE_ID:
            self.DoFindText()
            return True
        elif id == FindService.FindService.REPLACEONE_ID:
            self.DoReplaceSel()
            return True
        elif id == FindService.FindService.REPLACEALL_ID:
            self.DoReplaceAll()
            return True
        elif id == FindService.FindService.GOTO_LINE_ID:
            self.OnGotoLine(event)
            return True
        else:
            return wx.lib.docview.View.ProcessEvent(self, event)


    def ProcessUpdateUIEvent(self, event):
        if not self.GetCtrl():
            return False

        id = event.GetId()
        if id == wx.ID_UNDO:
            event.Enable(self.GetCtrl().CanUndo())
            event.SetText(_("&Undo\tCtrl+Z"))  # replace menu string
            return True
        elif id == wx.ID_REDO:
            event.Enable(self.GetCtrl().CanRedo())
            event.SetText(_("&Redo\tCtrl+Y"))  # replace menu string
            return True
        elif (id == wx.ID_CUT
        or id == wx.ID_COPY
        or id == wx.ID_CLEAR):
            event.Enable(self.HasSelection())
            return True
        elif id == wx.ID_PASTE:
            event.Enable(self.GetCtrl().CanPaste())
            return True
        elif id == wx.ID_SELECTALL:
            hasText = self.GetCtrl().GetTextLength() > 0
            event.Enable(hasText)
            return True
        elif id == TextService.TEXT_ID \
                or id == MarkerService.MarkerService.BOOKMARKER_ID \
                or id == TextService.INSERT_TEXT_ID \
                or id == TextService.ADVANCE_EDIT_ID \
                or id == TextService.ZOOM_ID \
                or id == TextService.CHOOSE_FONT_ID:
            event.Enable(True)
            return True
        elif id == TextService.VIEW_WHITESPACE_ID:
            hasText = self.GetCtrl().GetTextLength() > 0
            event.Enable(hasText)
            event.Check(self.GetCtrl().GetViewWhiteSpace())
            return True
        elif id == TextService.VIEW_EOL_ID:
            hasText = self.GetCtrl().GetTextLength() > 0
            event.Enable(hasText)
            event.Check(self.GetCtrl().GetViewEOL())
            return True
        elif id == TextService.VIEW_INDENTATION_GUIDES_ID:
            hasText = self.GetCtrl().GetTextLength() > 0
            event.Enable(hasText)
            event.Check(self.GetCtrl().GetIndentationGuides())
            return True
        elif id == TextService.VIEW_RIGHT_EDGE_ID:
            hasText = self.GetCtrl().GetTextLength() > 0
            event.Enable(hasText)
            event.Check(self.GetCtrl().GetViewRightEdge())
            return True
        elif id == TextService.VIEW_LINE_NUMBERS_ID:
            hasText = self.GetCtrl().GetTextLength() > 0
            event.Enable(hasText)
            event.Check(self.GetCtrl().GetViewLineNumbers())
            return True
        elif id == TextService.ZOOM_NORMAL_ID:
            event.Enable(self.GetCtrl().GetZoom() != 0)
            return True
        elif id == TextService.ZOOM_IN_ID:
            event.Enable(self.GetCtrl().GetZoom() < 20)
            return True
        elif id == TextService.ZOOM_OUT_ID:
            event.Enable(self.GetCtrl().GetZoom() > -10)
            return True
        elif id == TextService.WORD_WRAP_ID:
            event.Enable(self.GetCtrl().CanWordWrap())
            event.Check(self.GetCtrl().CanWordWrap() and self.GetCtrl().GetWordWrap())
            return True
        elif id == FindService.FindService.FIND_ID:
            hasText = self.GetCtrl().GetTextLength() > 0
            event.Enable(hasText)
            return True
        elif id == FindService.FindService.FIND_PREVIOUS_ID:
            hasText = self.GetCtrl().GetTextLength() > 0
            event.Enable(hasText and
                         self._FindServiceHasString() and
                         self.GetCtrl().GetSelection()[0] > 0)
            return True
        elif id == FindService.FindService.FIND_NEXT_ID:
            hasText = self.GetCtrl().GetTextLength() > 0
            event.Enable(hasText and
                         self._FindServiceHasString() and
                         self.GetCtrl().GetSelection()[0] < self.GetCtrl().GetLength())
            return True
        elif id == FindService.FindService.REPLACE_ID:
            hasText = self.GetCtrl().GetTextLength() > 0
            event.Enable(hasText)
            return True
        elif id == FindService.FindService.GOTO_LINE_ID:
            event.Enable(True)
            return True
        elif id == TextService.TEXT_STATUS_BAR_ID:
            self.OnUpdateStatusBar(event)
            return True
        elif id == CompletionService.CompletionService.GO_TO_DEFINITION:
            event.Enable(self.GetCtrl().IsCaretLocateInWord())
            return True
        elif id == CompletionService.CompletionService.LIST_CURRENT_MEMBERS:
            event.Enable(self.GetCtrl().IsListMemberFlag(self.GetCtrl().GetCurrentPos()-1))
            return True
        else:
            return wx.lib.docview.View.ProcessUpdateUIEvent(self, event)


    def _GetParentFrame(self):
        return wx.GetTopLevelParent(self.GetFrame())

    def _GetActiveCtrl(self, parent):    
        """ Walk through the MultiSash windows and find the active Control """   
        if isinstance(parent, wx.lib.multisash.MultiClient) and parent.selected:         
            return parent.child  
        if hasattr(parent, "GetChildren"):       
            for child in parent.GetChildren():   
                found = self._GetActiveCtrl(child)       
                if found:        
                    return found         
        return None      

         
    def _FindCtrl(self, parent):         
        """ Walk through the MultiSash windows and find the first TextCtrl """   
        if isinstance(parent, self.GetCtrlClass()):      
            return parent        
        if hasattr(parent, "GetChildren"):       
            for child in parent.GetChildren():   
                found = self._FindCtrl(child)    
                if found:        
                    return found         
        return None      
 

    #----------------------------------------------------------------------------
    # Methods for TextDocument to call
    #----------------------------------------------------------------------------

    def IsModified(self):
        if not self.GetCtrl():
            return False
        return self.GetCtrl().GetModify()


    def SetModifyFalse(self):
        self.GetCtrl().SetSavePoint()


    def GetValue(self):
        if self.GetCtrl():
            return self.GetCtrl().GetText()
        else:
            return None

    def SetBinaryValue(self,bytes_value):
        self.GetCtrl().AddStyledText(bytes_value)
        self.GetCtrl().SetReadOnly(True)
        
    def SetValue(self, value):
        self.GetCtrl().SetText(value)
        self.GetCtrl().UpdateLineNumberMarginWidth()
        self.GetCtrl().EmptyUndoBuffer()

    def AddText(self,text):
        self.GetCtrl().AddText(text)

    def HasSelection(self):
        return self.GetCtrl().HasSelection()

    def GetTopLines(self,line_num):
        lines = []
        for i in range(line_num):
            lines.append(self.GetCtrl().GetLine(i))
        return lines
    #----------------------------------------------------------------------------
    # STC events
    #----------------------------------------------------------------------------

    def OnUpdateStatusBar(self, event):
        statusBar = self._GetParentFrame().GetStatusBar()
        statusBar.SetInsertMode(self.GetCtrl().GetOvertype() == 0)
        statusBar.SetLineNumber(self.GetCtrl().GetCurrentLine() + 1)
        statusBar.SetColumnNumber(self.GetCtrl().GetColumn(self.GetCtrl().GetCurrentPos()) + 1)
        statusBar.SetDocumentEncoding(self.GetDocument().file_encoding)


    #----------------------------------------------------------------------------
    # Format methods
    #----------------------------------------------------------------------------

    def OnChooseFont(self):
        data = wx.FontData()
        data.EnableEffects(True)
        data.SetInitialFont(self.GetCtrl().GetFont())
        data.SetColour(self.GetCtrl().GetFontColor())
        fontDialog = wx.FontDialog(self.GetFrame(), data)
        fontDialog.CenterOnParent()
        if fontDialog.ShowModal() == wx.ID_OK:
            data = fontDialog.GetFontData()
            self.GetCtrl().SetFont(data.GetChosenFont())
            self.GetCtrl().SetFontColor(data.GetColour())
            self.GetCtrl().UpdateStyles()
        fontDialog.Destroy()


    #----------------------------------------------------------------------------
    # Find methods
    #----------------------------------------------------------------------------

    def OnFind(self, replace = False):
        findService = wx.GetApp().GetService(FindService.FindService)
        if findService:
            findService.ShowFindReplaceDialog(findString = self.GetCtrl().GetSelectedText(), replace = replace)

    def AdjustFindDialogPosition(self,findService):
        start = self.GetCtrl().GetSelectionEnd()
        point = self.GetCtrl().PointFromPosition(start)
        new_point = self.GetCtrl().ClientToScreen(point)
        current_dlg = findService.GetCurrentDialog()
        dlg_rect = current_dlg.GetRect()
        if dlg_rect.Contains(new_point):
            if new_point.y > dlg_rect.GetHeight():
                dlg_rect.Offset(wx.Point(0,new_point.y-20-dlg_rect.GetBottomRight().y))
            else:
                dlg_rect.Offset(wx.Point(0,new_point.y+40-dlg_rect.GetTopLeft().y))
            to_point = wx.Point(dlg_rect.GetX(),dlg_rect.GetY())
            current_dlg.Move(to_point)
        
    def DoFindText(self,forceFindNext = False, forceFindPrevious = False):
        findService = wx.GetApp().GetService(FindService.FindService)
        if not findService:
            return
        findString = findService.GetFindString()
        if len(findString) == 0:
            return -1
        flags = findService.GetFlags()
        if not self.GetCtrl().DoFindText(findString,flags,forceFindNext,forceFindPrevious):
            self.GetCtrl().TextNotFound(findString,flags,forceFindNext,forceFindPrevious)
        else:
            if not forceFindNext and not forceFindPrevious:
                self.AdjustFindDialogPosition(findService)
            
    def DoReplaceSel(self):
        findService = wx.GetApp().GetService(FindService.FindService)
        if not findService:
            return
        findString = findService.GetFindString()
        if len(findString) == 0:
            return -1
        replaceString = findService.GetReplaceString()
        flags = findService.GetFlags()
        if not self.SameAsSelected(findString,flags):
            if not self.GetCtrl().DoFindText(findString,flags):
                self.GetCtrl().TextNotFound(findString,flags)
            else:
                self.AdjustFindDialogPosition(findService)
            return
        self.GetCtrl().ReplaceSelection(replaceString)
        if not self.GetCtrl().DoFindText(findString,flags):
            self.GetCtrl().TextNotFound(findString,flags)
        else:
            self.AdjustFindDialogPosition(findService)
      
    def DoReplaceAll(self):
        findService = wx.GetApp().GetService(FindService.FindService)
        if not findService:
            return
        findString = findService.GetFindString()
        if len(findString) == 0:
            return -1
        replaceString = findService.GetReplaceString()
        flags = findService.GetFlags()
        hit_found = False
        self.GetCtrl().SetSelection(0,0)
        ###self.GetCtrl().HideSelection(True)
        while self.GetCtrl().DoFindText(findString,flags):
            hit_found = True
            self.GetCtrl().ReplaceSelection(replaceString)

        ###self.GetCtrl().HideSelection(False)
        if not hit_found:
            self.GetCtrl().TextNotFound(findString,flags)
        
    def SameAsSelected(self,findString,flags):
        start_pos = self.GetCtrl().GetSelectionStart()
        end_pos = self.GetCtrl().GetSelectionEnd()
        wholeWord = flags & wx.FR_WHOLEWORD > 0
        matchCase = flags & wx.FR_MATCHCASE > 0
        regExp = flags & FindService.FindService.FR_REGEXP > 0
        flags =  wx.stc.STC_FIND_MATCHCASE if matchCase else 0
        flags |= wx.stc.STC_FIND_WHOLEWORD if wholeWord else 0
        flags |= wx.stc.STC_FIND_REGEXP if regExp else 0
        #Now use the advanced search functionality of scintilla to determine the result
        self.GetCtrl().SetSearchFlags(flags);
        self.GetCtrl().TargetFromSelection();
        #see what we got
        if self.GetCtrl().SearchInTarget(findString) < 0:
            #no match
            return False
        	#If we got a match, the target is set to the found text
        return (self.GetCtrl().GetTargetStart() == start_pos) and (self.GetCtrl().GetTargetEnd() == end_pos);
        
    def FindTextInLine(self,text,line,col=0):
        line_start = self.GetCtrl().PositionFromLine(line-1)
        line_start += col
        line_end = self.GetCtrl().PositionFromLine(line)
        index = self.GetCtrl().FindText(line_start,line_end,text,0)
        if -1 != index:
            return index,index + len(text)
        return -1,-1

    def _FindServiceHasString(self):
        findService = wx.GetApp().GetService(FindService.FindService)
        if not findService or not findService.GetFindString():
            return False
        return True

    def OnGotoLine(self, event):
        findService = wx.GetApp().GetService(FindService.FindService)
        if findService:
            line_number = self.GetCtrl().GetLineCount()
            line = findService.GetLineNumber(self.GetDocumentManager().FindSuitableParent(),line_number)
            self.GotoLine(line)
           # if line > -1:
           #    line = line - 1
           #    self.GetCtrl().EnsureVisible(line)
           #    self.GetCtrl().GotoLine(line)

    @NavigationService.jumpto
    def GotoLine(self, lineNum):
        if lineNum > -1:
            lineNum = lineNum - 1  # line numbering for editor is 0 based, we are 1 based.
            self.GetCtrl().EnsureVisibleEnforcePolicy(lineNum)
            self.GetCtrl().GotoLine(lineNum)

    @NavigationService.jumpto
    def GotoPos(self, pos):
        if pos > -1:
            self.GetCtrl().GotoPos(pos)

    def SetSelection(self, start, end):
        self.GetCtrl().SetSelection(start, end)

    def EnsureVisible(self, line):
        self.GetCtrl().EnsureVisible(line-1)  # line numbering for editor is 0 based, we are 1 based.

    def EnsureVisibleEnforcePolicy(self, line):
        self.GetCtrl().EnsureVisibleEnforcePolicy(line-1)  # line numbering for editor is 0 based, we are 1 based.

    def GetLineCount(self):
        return self.GetCtrl().GetLineCount()
        
    def LineFromPosition(self, pos):
        return self.GetCtrl().LineFromPosition(pos)+1  # line numbering for editor is 0 based, we are 1 based.

    def PositionFromLine(self, line):
        return self.GetCtrl().PositionFromLine(line-1)  # line numbering for editor is 0 based, we are 1 based.

    def GetLineEndPosition(self, line):
        return self.GetCtrl().GetLineEndPosition(line-1)  # line numbering for editor is 0 based, we are 1 based.

    def GetLine(self, lineNum):
        return self.GetCtrl().GetLine(lineNum-1)  # line numbering for editor is 0 based, we are 1 based.

    def MarkerDefine(self):
        """ This must be called after the texteditor is instantiated """
        self.GetCtrl().MarkerDefine(TextView.BOOK_MARKER_NUM, wx.stc.STC_MARK_CIRCLE, wx.BLACK, wx.BLUE)

    def MarkerToggle(self, lineNum = -1, marker_index=BOOK_MARKER_NUM, mask=BOOK_MARKER_MASK):
        if lineNum == -1:
            lineNum = self.GetCtrl().GetCurrentLine()
        if self.GetCtrl().MarkerGet(lineNum) & mask:
            self.GetCtrl().MarkerDelete(lineNum, marker_index)
            self._markerCount -= 1
        else:
            self.GetCtrl().MarkerAdd(lineNum, marker_index)
            self._markerCount += 1

    def MarkerAdd(self, lineNum = -1, marker_index=BOOK_MARKER_NUM, mask=BOOK_MARKER_MASK):
        if lineNum == -1:
            lineNum = self.GetCtrl().GetCurrentLine()
        self.GetCtrl().MarkerAdd(lineNum, marker_index)
        self._markerCount += 1

    def MarkerDelete(self, lineNum = -1, marker_index=BOOK_MARKER_NUM, mask=BOOK_MARKER_MASK):
        if lineNum == -1:
            lineNum = self.GetCtrl().GetCurrentLine()
        if self.GetCtrl().MarkerGet(lineNum) & mask:
            self.GetCtrl().MarkerDelete(lineNum, marker_index)
            self._markerCount -= 1

    def MarkerDeleteAll(self, marker_num=BOOK_MARKER_NUM):
        self.GetCtrl().MarkerDeleteAll(marker_num)
        if marker_num == self.BOOK_MARKER_NUM:
            self._markerCount = 0

    def MarkerNext(self, lineNum = -1):
        if lineNum == -1:
            lineNum = self.GetCtrl().GetCurrentLine() + 1  # start search below current line
        foundLine = self.GetCtrl().MarkerNext(lineNum, self.BOOK_MARKER_MASK)
        if foundLine == -1:
            # wrap to top of file
            foundLine = self.GetCtrl().MarkerNext(0, self.BOOK_MARKER_MASK)
            if foundLine == -1:
                wx.GetApp().GetTopWindow().PushStatusText(_("No markers"))
                return        
        self.GotoLine(foundLine + 1)

    def MarkerPrevious(self, lineNum = -1):
        if lineNum == -1:
            lineNum = self.GetCtrl().GetCurrentLine() - 1  # start search above current line
            if lineNum == -1:
                lineNum = self.GetCtrl().GetLineCount()

        foundLine = self.GetCtrl().MarkerPrevious(lineNum, self.BOOK_MARKER_MASK)
        if foundLine == -1:
            # wrap to bottom of file
            foundLine = self.GetCtrl().MarkerPrevious(self.GetCtrl().GetLineCount(), self.BOOK_MARKER_MASK)
            if foundLine == -1:
                wx.GetApp().GetTopWindow().PushStatusText(_("No markers"))
                return
        self.GotoLine(foundLine + 1)

    def MarkerExists(self, lineNum = -1, mask=BOOK_MARKER_MASK):
        if lineNum == -1:
            lineNum = self.GetCtrl().GetCurrentLine()
        if self.GetCtrl().MarkerGet(lineNum) & mask:
            return True
        else:
            return False

    def GetMarkerLines(self, mask=BOOK_MARKER_MASK):
        retval = []
        for lineNum in range(self.GetCtrl().GetLineCount()):
            if self.GetCtrl().MarkerGet(lineNum) & mask:
                retval.append(lineNum)
        return retval
        
    def GetMarkerCount(self):
        return self._markerCount

    @WxThreadSafe.call_after
    def Alarm(self,alarm_type):
        #to avoid alarm many times
        if self._is_alarming and alarm_type == self._alarm_type:
            utils.GetLogger().warn("document %s is alarming,will not alarm again" % self.GetDocument().GetFilename())
            return
        self._is_alarming = True
        self._alarm_type = alarm_type
        if alarm_type == FileObserver.FileEventHandler.FILE_MODIFY_EVENT:
            ret = wx.MessageBox(_("File \"%s\" has already been modified outside,Do You Want to reload it?") % self.GetDocument().GetFilename(), _("Reload.."),
                           wx.YES_NO  | wx.ICON_QUESTION,self.GetFrame())
            if ret == wx.YES:
                document = self.GetDocument()
                document.OnOpenDocument(document.GetFilename())
                
        elif alarm_type == FileObserver.FileEventHandler.FILE_MOVED_EVENT or \
             alarm_type == FileObserver.FileEventHandler.FILE_DELETED_EVENT:
            ret = wx.MessageBox(_("File \"%s\" has already been moved or deleted outside,Do You Want to keep it in Editor?") % self.GetDocument().GetFilename(), _("Keep Document.."),
                           wx.YES_NO  | wx.ICON_QUESTION ,self.GetFrame())
            document = self.GetDocument()
            if ret == wx.YES:
                document.Modify(True)
            else:
                document.DeleteAllViews()
        self._is_alarming = False

    def IsUnitTestEnable(self):
        return False

class TextOptionsPanel(wx.Panel):

    def __init__(self, parent, id, size,configPrefix = "Text", label = "Text", hasWordWrap = True, hasTabs = True, addPage=True, hasFolding=True):
        wx.Panel.__init__(self, parent, id,size=size)
        self._configPrefix = configPrefix
        self._hasWordWrap = hasWordWrap
        self._hasTabs = hasTabs
        self._hasFolding = hasFolding
        SPACE = 10
        HALF_SPACE   = 5
        config = wx.ConfigBase_Get()
        fontData = config.Read(consts.PRIMARY_FONT_KEY, "")
        if fontData:
            font_data = json.loads(fontData)
            self._textFont =  wx.Font(font_data['size'],wx.FONTFAMILY_MODERN, wx.FONTSTYLE_NORMAL,\
                                      wx.FONTWEIGHT_NORMAL,faceName=font_data['font'])
        else:
            self._textFont = wx.Font(consts.DEFAULT_FONT_SIZE, wx.MODERN, wx.NORMAL, wx.NORMAL,\
                                     faceName = consts.DEFAULT_FONT_NAME)
        self._originalTextFont = self._textFont
        global_style = syntax.LexerManager().GetGlobalItemByName(consts.GLOBAL_STYLE_NAME)
        global_style.GetStyleSpec()
        rgb = strutils.HexToRGB(global_style.Fore)
        self._textColor = wx.Colour(red=rgb[0], green=rgb[1], blue=rgb[2])
        self._originalTextColor = self._textColor
        fontLabel = wx.StaticText(self, -1, _("Font:"))
        self._sampleTextCtrl = wx.TextCtrl(self, -1, "", size = (125, 21))
        self._sampleTextCtrl.SetEditable(False)
        chooseFontButton = wx.Button(self, -1, _("Choose Font..."))
        wx.EVT_BUTTON(self, chooseFontButton.GetId(), self.OnChooseFont)
        if self._hasWordWrap:
            self._wordWrapCheckBox = wx.CheckBox(self, -1, _("Wrap words inside text area"))
            self._wordWrapCheckBox.SetValue(wx.ConfigBase_Get().ReadInt(self._configPrefix + "EditorWordWrap", False))
        self._viewWhitespaceCheckBox = wx.CheckBox(self, -1, _("Show whitespace"))
        self._viewWhitespaceCheckBox.SetValue(config.ReadInt(self._configPrefix + "EditorViewWhitespace", False))
        self._viewEOLCheckBox = wx.CheckBox(self, -1, _("Show end of line markers"))
        self._viewEOLCheckBox.SetValue(config.ReadInt(self._configPrefix + "EditorViewEOL", False))
        self._viewIndentationGuideCheckBox = wx.CheckBox(self, -1, _("Show indentation guides"))
        self._viewIndentationGuideCheckBox.SetValue(config.ReadInt(self._configPrefix + "EditorViewIndentationGuides", False))
        self._viewRightEdgeCheckBox = wx.CheckBox(self, -1, _("Show right edge"))
        self.Bind(wx.EVT_CHECKBOX,self.CheckRightEdge,self._viewRightEdgeCheckBox)
        self._viewRightEdgeCheckBox.SetValue(config.ReadInt(self._configPrefix + "EditorViewRightEdge", False))
        self._viewLineNumbersCheckBox = wx.CheckBox(self, -1, _("Show line numbers"))
        self._viewLineNumbersCheckBox.SetValue(config.ReadInt(self._configPrefix + "EditorViewLineNumbers", True))
        if self._hasFolding:
            self._viewFoldingCheckBox = wx.CheckBox(self, -1, _("Show folding"))
            self._viewFoldingCheckBox.SetValue(config.ReadInt(self._configPrefix + "EditorViewFolding", True))
        self._highlightCaretLineCheckBox = wx.CheckBox(self, -1, _("Highlight Caret Line"))
        self._highlightCaretLineCheckBox.SetValue(config.ReadInt(self._configPrefix + "EditorHighlightCaretLine", True))
        if self._hasTabs:
            self._hasTabsCheckBox = wx.CheckBox(self, -1, _("Use spaces instead of tabs"))
            self._hasTabsCheckBox.SetValue(not wx.ConfigBase_Get().ReadInt(self._configPrefix + "EditorUseTabs", False))
            indentWidthLabel = wx.StaticText(self, -1, _("Indent Width:"))
            self._indentWidthChoice = wx.Choice(self, -1, choices = ["2", "4", "6", "8", "10"])
            self._indentWidthChoice.SetStringSelection(str(config.ReadInt(self._configPrefix + "EditorIndentWidth", 4)))
        edgeWidthLabel = wx.StaticText(self, -1, _("Edge Guide Width:"))
        self.edge_spin_ctrl = wx.SpinCtrl(self, -1,str(utils.ProfileGetInt('EdgeGuideWidth',consts.DEFAULT_EDGE_GUIDE_WIDTH)), min=0, max=160)
        defaultEOLModelLabel = wx.StaticText(self, -1, _("Default EOL Mode:"))
        self.eol_model_combox = wx.ComboBox(self, -1,choices=EOLFormat.EOLFormatDlg.EOL_CHOICES,style= wx.CB_READONLY)
        if sysutilslib.isWindows():
            eol_mode = config.ReadInt(self._configPrefix + "EditorEOLMode", wx.stc.STC_EOL_CRLF)
        else:
            eol_mode = config.ReadInt(self._configPrefix + "EditorEOLMode", wx.stc.STC_EOL_LF)
        idx = EOLFormat.EOLFormatDlg.EOL_ITEMS.index(eol_mode)
        self.eol_model_combox.SetSelection(idx)
        
        textPanelBorderSizer = wx.BoxSizer(wx.VERTICAL)
        textPanelSizer = wx.BoxSizer(wx.VERTICAL)
        textFontSizer = wx.BoxSizer(wx.HORIZONTAL)
        textFontSizer.Add(fontLabel, 0, wx.ALIGN_LEFT | wx.RIGHT | wx.TOP, HALF_SPACE)
        textFontSizer.Add(self._sampleTextCtrl, 1, wx.ALIGN_LEFT | wx.EXPAND | wx.RIGHT, HALF_SPACE)
        textFontSizer.Add(chooseFontButton, 0, wx.ALIGN_RIGHT | wx.LEFT, HALF_SPACE)
        textPanelSizer.Add(textFontSizer, 0, wx.ALL|wx.EXPAND, HALF_SPACE)
        if self._hasWordWrap:
            textPanelSizer.Add(self._wordWrapCheckBox, 0, wx.ALL, HALF_SPACE)
        textPanelSizer.Add(self._viewWhitespaceCheckBox, 0, wx.ALL, HALF_SPACE)
        textPanelSizer.Add(self._viewEOLCheckBox, 0, wx.ALL, HALF_SPACE)
        textPanelSizer.Add(self._viewIndentationGuideCheckBox, 0, wx.ALL, HALF_SPACE)
        textPanelSizer.Add(self._viewRightEdgeCheckBox, 0, wx.ALL, HALF_SPACE)
        textPanelSizer.Add(self._viewLineNumbersCheckBox, 0, wx.ALL, HALF_SPACE)
        if self._hasFolding:
            textPanelSizer.Add(self._viewFoldingCheckBox, 0, wx.ALL, HALF_SPACE)
        textPanelSizer.Add(self._highlightCaretLineCheckBox, 0, wx.ALL, HALF_SPACE)
        if self._hasTabs:
            textPanelSizer.Add(self._hasTabsCheckBox, 0, wx.ALL, HALF_SPACE)
            textIndentWidthSizer = wx.BoxSizer(wx.HORIZONTAL)
            textIndentWidthSizer.Add(indentWidthLabel, 0, wx.ALIGN_LEFT | wx.RIGHT | wx.TOP, HALF_SPACE)
            textIndentWidthSizer.Add(self._indentWidthChoice, 0, wx.ALIGN_LEFT | wx.EXPAND, HALF_SPACE)
            textPanelSizer.Add(textIndentWidthSizer, 0, wx.ALL, HALF_SPACE)
            
        line_sizer = wx.BoxSizer(wx.HORIZONTAL)
        line_sizer.Add(edgeWidthLabel, 0, wx.ALIGN_LEFT | wx.RIGHT | wx.TOP, HALF_SPACE)
        line_sizer.Add(self.edge_spin_ctrl, 0, wx.ALIGN_LEFT | wx.EXPAND, HALF_SPACE)
        textPanelSizer.Add(line_sizer, 0, wx.ALL, HALF_SPACE)
        self.CheckRightEdge(None)
        
        line_sizer = wx.BoxSizer(wx.HORIZONTAL)
        line_sizer.Add(defaultEOLModelLabel, 0, wx.ALIGN_LEFT | wx.RIGHT | wx.TOP, HALF_SPACE)
        line_sizer.Add(self.eol_model_combox, 0, wx.ALIGN_LEFT | wx.EXPAND, HALF_SPACE)
        textPanelSizer.Add(line_sizer, 0, wx.ALL, HALF_SPACE)
        
        textPanelBorderSizer.Add(textPanelSizer, 0, wx.ALL|wx.EXPAND, SPACE)
##        styleButton = wx.Button(self, -1, _("Choose Style..."))
##        wx.EVT_BUTTON(self, styleButton.GetId(), self.OnChooseStyle)
##        textPanelBorderSizer.Add(styleButton, 0, wx.ALL, SPACE)
        self.SetSizer(textPanelBorderSizer)
        self.UpdateSampleFont()
        
    def CheckRightEdge(self,event):
        self.edge_spin_ctrl.Enable(self._viewRightEdgeCheckBox.GetValue())

    def UpdateSampleFont(self):
        nativeFont = wx.NativeFontInfo()
        nativeFont.FromString(self._textFont.GetNativeFontInfoDesc())
        font = wx.NullFont
        font.SetNativeFontInfo(nativeFont)
        font.SetPointSize(self._sampleTextCtrl.GetFont().GetPointSize())  # Use the standard point size
        self._sampleTextCtrl.SetFont(font)
        self._sampleTextCtrl.SetForegroundColour(self._textColor)
        self._sampleTextCtrl.SetValue(str(self._textFont.GetPointSize()) + _(" pt. ") + self._textFont.GetFaceName())
        self._sampleTextCtrl.Refresh()
        self.Layout()


##    def OnChooseStyle(self, event):
##        import STCStyleEditor
##        import os
##        base = os.path.split(__file__)[0]
##        config = os.path.abspath(os.path.join(base, 'stc-styles.rc.cfg'))
##        
##        dlg = STCStyleEditor.STCStyleEditDlg(None,
##                                'Python', 'python',
##                                #'HTML', 'html',
##                                #'XML', 'xml',
##                                config)
##        dlg.CenterOnParent()
##        try:
##            dlg.ShowModal()
##        finally:
##            dlg.Destroy()


    def OnChooseFont(self, event):
        data = wx.FontData()
        data.EnableEffects(True)
        data.SetInitialFont(self._textFont)
        data.SetColour(self._textColor)
        fontDialog = wx.FontDialog(self, data)
        fontDialog.CenterOnParent()
        if fontDialog.ShowModal() == wx.ID_OK:
            data = fontDialog.GetFontData()
            self._textFont = data.GetChosenFont()
            self._textColor = data.GetColour()
            self.UpdateSampleFont()
        fontDialog.Destroy()


    def OnOK(self, optionsDialog):
        config = wx.ConfigBase_Get()
        doViewStuffUpdate = config.ReadInt(self._configPrefix + "EditorViewWhitespace", False) != self._viewWhitespaceCheckBox.GetValue()
        config.WriteInt(self._configPrefix + "EditorViewWhitespace", self._viewWhitespaceCheckBox.GetValue())
        doViewStuffUpdate = doViewStuffUpdate or config.ReadInt(self._configPrefix + "EditorViewEOL", False) != self._viewEOLCheckBox.GetValue()
        config.WriteInt(self._configPrefix + "EditorViewEOL", self._viewEOLCheckBox.GetValue())
        doViewStuffUpdate = doViewStuffUpdate or config.ReadInt(self._configPrefix + "EditorViewIndentationGuides", False) != self._viewIndentationGuideCheckBox.GetValue()
        config.WriteInt(self._configPrefix + "EditorViewIndentationGuides", self._viewIndentationGuideCheckBox.GetValue())
        doViewStuffUpdate = doViewStuffUpdate or config.ReadInt(self._configPrefix + "EditorViewRightEdge", False) != self._viewRightEdgeCheckBox.GetValue()
        config.WriteInt(self._configPrefix + "EditorViewRightEdge", self._viewRightEdgeCheckBox.GetValue())
        doViewStuffUpdate = doViewStuffUpdate or config.ReadInt(self._configPrefix + "EditorViewLineNumbers", True) != self._viewLineNumbersCheckBox.GetValue()
        config.WriteInt(self._configPrefix + "EditorViewLineNumbers", self._viewLineNumbersCheckBox.GetValue())
        doViewStuffUpdate = doViewStuffUpdate or config.ReadInt(self._configPrefix + "EditorHighlightCaretLine", True) != self._highlightCaretLineCheckBox.GetValue()
        config.WriteInt(self._configPrefix + "EditorHighlightCaretLine", self._highlightCaretLineCheckBox.GetValue())
        if sysutilslib.isWindows():
            default_eol_mode = wx.stc.STC_EOL_CRLF
        else:
            default_eol_mode = wx.stc.STC_EOL_LF
        eol_mode = EOLFormat.EOLFormatDlg.EOL_ITEMS[self.eol_model_combox.GetSelection()]
        doViewStuffUpdate = doViewStuffUpdate or config.ReadInt(self._configPrefix + "EditorEOLMode", default_eol_mode) != eol_mode
        config.WriteInt(self._configPrefix + "EditorEOLMode", eol_mode)
        if self._viewRightEdgeCheckBox.GetValue():
            doViewStuffUpdate = doViewStuffUpdate or config.ReadInt("EdgeGuideWidth", consts.DEFAULT_EDGE_GUIDE_WIDTH) != int(self.edge_spin_ctrl.GetValue())
            config.WriteInt("EdgeGuideWidth", int(self.edge_spin_ctrl.GetValue()))
        if self._hasFolding:
            doViewStuffUpdate = doViewStuffUpdate or config.ReadInt(self._configPrefix + "EditorViewFolding", True) != self._viewFoldingCheckBox.GetValue()
            config.WriteInt(self._configPrefix + "EditorViewFolding", self._viewFoldingCheckBox.GetValue())
        if self._hasWordWrap:
            doViewStuffUpdate = doViewStuffUpdate or config.ReadInt(self._configPrefix + "EditorWordWrap", False) != self._wordWrapCheckBox.GetValue()
            config.WriteInt(self._configPrefix + "EditorWordWrap", self._wordWrapCheckBox.GetValue())
        if self._hasTabs:
            doViewStuffUpdate = doViewStuffUpdate or not config.ReadInt(self._configPrefix + "EditorUseTabs", True) != self._hasTabsCheckBox.GetValue()
            config.WriteInt(self._configPrefix + "EditorUseTabs", not self._hasTabsCheckBox.GetValue())
            newIndentWidth = int(self._indentWidthChoice.GetStringSelection())
            oldIndentWidth = config.ReadInt(self._configPrefix + "EditorIndentWidth", 4)
            if newIndentWidth != oldIndentWidth:
                doViewStuffUpdate = True
                config.WriteInt(self._configPrefix + "EditorIndentWidth", newIndentWidth)
        doFontUpdate = self._originalTextFont != self._textFont or self._originalTextColor != self._textColor
        if doFontUpdate:
            data_str = json.dumps({'font':self._textFont.GetFaceName(),'size':self._textFont.GetPointSize()})
            config.Write(consts.PRIMARY_FONT_KEY, data_str)
            config.Write(self._configPrefix + "EditorColor", "%02x%02x%02x" % (self._textColor.Red(), self._textColor.Green(), self._textColor.Blue()))
            font, color = syntax.LexerManager().GetFontAndColorFromConfig()
            syntax.LexerManager().SetGlobalFont(font.GetFaceName(),font.GetPointSize())
            syntax.LexerManager().SetGlobalFontColor("",strutils.RGBToHex(color))
        if doViewStuffUpdate or doFontUpdate:
            for document in optionsDialog.GetDocManager().GetDocuments():
                if issubclass(document.GetDocumentTemplate().GetDocumentType(), TextDocument):
                    if doViewStuffUpdate:
                        document.UpdateAllViews(hint = "ViewStuff")
                    if doFontUpdate:
                        document.UpdateAllViews(hint = "Font")
        return True
               
         
    def GetIcon(self):
        return getTextIcon()

class TextCtrl(FindTextCtrl.FindTextCtrl):

    def __init__(self, parent, id=-1,style=wx.NO_FULL_REPAINT_ON_RESIZE):
        FindTextCtrl.FindTextCtrl.__init__(self, parent, id, style=style)
        self.UpdateBaseStyles()
        self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
        self.Bind(wx.stc.EVT_STC_ZOOM, self.OnUpdateLineNumberMarginWidth)  # auto update line num width on zoom
        self.MarkerDefineDefault()
      #  self.SetEdgeMode(wx.stc.STC_EDGE_LINE)
        self.SetEdgeColumn(utils.ProfileGetInt("EdgeGuideWidth",consts.DEFAULT_EDGE_GUIDE_WIDTH))
        

    @NavigationService.jumpaction
    def OnLeftUp(self, evt):
        """Set primary selection and inform mainwindow that cursor position
        has changed.
        @param evt: wx.MouseEvent()
        """
        evt.Skip()
        
    def SetCaretLineColor(self,color):
        caretline_visbile = utils.ProfileGetInt("TextEditorHighlightCaretLine",True)
        if caretline_visbile:
            FindTextCtrl.FindTextCtrl.SetCaretLineColor(self,color)
        else:
            self.SetCaretLineVisible(False)
        
    def GetViewLineNumbers(self):
        return self.GetMarginWidth(TextView.LINE_MARKER_NUM) > 0

    def SetViewLineNumbers(self, viewLineNumbers = True):
        if viewLineNumbers:
            self.SetMarginWidth(TextView.LINE_MARKER_NUM, self.EstimatedLineNumberMarginWidth())
        else:
            self.SetMarginWidth(TextView.LINE_MARKER_NUM, 0)

    def GetViewFolding(self):
        return self.GetMarginWidth(TextView.FOLD_MARKER_NUM) > 0

    def SetViewFolding(self, viewFolding = True):
        if viewFolding:
            self.SetMarginWidth(TextView.FOLD_MARKER_NUM, TextView.FOLD_MARGIN_WIDTH)
        else:
            self.SetMarginWidth(TextView.FOLD_MARKER_NUM, 0)
            
    def GetFontAndColorFromConfig(self, configPrefix = "Text"):
        return syntax.LexerManager().GetFontAndColorFromConfig()

    def SetViewDefaults(self, configPrefix="Text", hasWordWrap=True, hasTabs=True, hasFolding=True):
        config = wx.ConfigBase_Get()
        self.SetViewWhiteSpace(config.ReadInt(configPrefix + "EditorViewWhitespace", False))
        self.SetViewEOL(config.ReadInt(configPrefix + "EditorViewEOL", False))
        self.SetIndentationGuides(config.ReadInt(configPrefix + "EditorViewIndentationGuides", False))
        self.SetViewRightEdge(config.ReadInt(configPrefix + "EditorViewRightEdge", False))
        self.SetViewLineNumbers(config.ReadInt(configPrefix + "EditorViewLineNumbers", True))
        if hasFolding:
            self.SetViewFolding(config.ReadInt(configPrefix + "EditorViewFolding", True))
        if hasWordWrap:
            self.SetWordWrap(config.ReadInt(configPrefix + "EditorWordWrap", False))
        if hasTabs:  # These methods do not exist in STCTextEditor and are meant for subclasses
            self.SetUseTabs(config.ReadInt(configPrefix + "EditorUseTabs", False))
            self.SetIndent(config.ReadInt(configPrefix + "EditorIndentWidth", 4))
            self.SetTabWidth(config.ReadInt(configPrefix + "EditorIndentWidth", 4))
        else:
            self.SetUseTabs(True)
            self.SetIndent(4)
            self.SetTabWidth(4)
        self.SetEdgeColumn(config.ReadInt("EdgeGuideWidth",consts.DEFAULT_EDGE_GUIDE_WIDTH))
        self.SetCaretLineVisible(config.ReadInt(configPrefix + "EditorHighlightCaretLine", True))
        if sysutilslib.isWindows():
            default_eol_mode = wx.stc.STC_EOL_CRLF
        else:
            default_eol_mode = wx.stc.STC_EOL_LF
        self.SetEOLMode(config.ReadInt(configPrefix + "EditorEOLMode", default_eol_mode))
        
    def OnUpdateLineNumberMarginWidth(self, event):
        self.UpdateLineNumberMarginWidth()
            
    def UpdateLineNumberMarginWidth(self):
        if self.GetViewLineNumbers():
            self.SetMarginWidth(TextView.LINE_MARKER_NUM, self.EstimatedLineNumberMarginWidth())
        
    def MarkerDefineDefault(self):
        """ This must be called after the textcontrol is instantiated """
        self.MarkerDefine(TextView.BOOK_MARKER_NUM, wx.stc.STC_MARK_ROUNDRECT, wx.BLACK, wx.BLUE)

    def IsCaretLocateInWord(self):
        return False

    def IsListMemberFlag(self,pos):
        return False

    def UpdateBaseStyles(self):
        """Updates the base styles of editor to the current settings
        @postcondition: base style info is updated

        """
        ####self.StyleDefault()
        self.SetMargins(4, 0)
        
        lex_manager = syntax.LexerManager()

        # Global default styles for all languages
        self.StyleSetSpec(0, lex_manager.GetGlobalStyleByName(consts.GLOBAL_STYLE_NAME))
        self.StyleSetSpec(wx.stc.STC_STYLE_DEFAULT, lex_manager.GetGlobalStyleByName(consts.GLOBAL_STYLE_NAME))
        global_style = lex_manager.GetGlobalItemByName(consts.GLOBAL_STYLE_NAME)
        self.StyleSetExAttr(wx.stc.STC_STYLE_DEFAULT,global_style)
        self.StyleDefault()
        self.StyleSetSpec(wx.stc.STC_STYLE_LINENUMBER, lex_manager.GetGlobalStyleByName('LineNumber'))
        self.StyleSetSpec(wx.stc.STC_STYLE_CONTROLCHAR, lex_manager.GetGlobalStyleByName('CtrlChar'))
        self.StyleSetSpec(wx.stc.STC_STYLE_BRACELIGHT, lex_manager.GetGlobalStyleByName('BraceLight'))
        self.StyleSetSpec(wx.stc.STC_STYLE_BRACEBAD, lex_manager.GetGlobalStyleByName('BraceBad'))
        self.StyleSetSpec(wx.stc.STC_STYLE_INDENTGUIDE, lex_manager.GetGlobalStyleByName('IndentGuideLine'))

        # wx.stc.STC_STYLE_CALLTIP doesn't seem to do anything
        calltip = lex_manager.GetItemByName('calltip')
        self.CallTipSetBackground(calltip.GetBack())
        self.CallTipSetForeground(calltip.GetFore())

        sback = lex_manager.GetItemByName('select_style')
        if not sback.IsNull() and len(sback.GetBack()):
            sback = sback.GetBack()
            sback = strutils.HexToRGB(sback)
            sback = wx.Colour(*sback)
        else:
            sback = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)

        # If selection colour is dark make the foreground white
        # else use the default settings.
        if sum(sback.Get()) < 384:
            self.SetSelForeground(True, wx.WHITE)
        else:
            self.SetSelForeground(True, wx.BLACK)
        self.SetSelBackground(True, sback)

        # Causes issues with selecting text when view whitespace is on
#        wspace = self.GetItemByName('whitespace_style')
#        self.SetWhitespaceBackground(True, wspace.GetBack())
#        self.SetWhitespaceForeground(True, wspace.GetFore())

        default_fore = self.GetDefaultForeColour()
        edge_colour = lex_manager.GetItemByName('edge_style')
        if sysutilslib.isWindows() and edge_colour.GetFore():
            self.SetEdgeColour(edge_colour.GetFore())
        self.SetCaretForeground(default_fore)
        self.SetCaretLineBack(lex_manager.GetItemByName('caret_line').GetBack())
        self.Colourise(0, -1)

    def SetSyntax(self, synlst):
        """Sets the Syntax Style Specs from a list of specifications
        @param synlst: [(STYLE_ID, "STYLE_TYPE"), (STYLE_ID2, "STYLE_TYPE2)]

        """
        # Parses Syntax Specifications list, ignoring all bad values
        self.UpdateBaseStyles()
        valid_settings = list()
        for syn in synlst:
            #if len(syn) != 2:
              #  self.LOG("[ed_style][warn] Bogus Syntax Spec %s" % repr(syn))
               # continue
            #else:
            self.StyleSetSpec(syn.StyleId, syn.GetStyleSpec())
            valid_settings.append(syn)
        syntax.LexerManager().syntax_set = valid_settings
        self.Refresh()
        return True

    def StyleDefault(self):
        """Clears the editor styles to default
        @postcondition: style is reset to default

        """
        self.StyleClearAll()
        self.SetCaretForeground(wx.BLACK)
        self.Colourise(0, -1)
        
    def GetDefaultForeColour(self, as_hex=False):
        """Gets the foreground color of the default style and returns
        a Colour object. Otherwise returns Black if the default
        style is not found.
        @keyword as_hex: return a hex string or colour object
        @return: wx.Colour of default style foreground or hex value

        """
        fore = syntax.LexerManager().GetItemByName('default_style').Fore
        if not fore:
            fore = u"#000000"

        if not as_hex:
            rgb = strutils.HexToRGB(fore[1:])
            fore = wx.Colour(red=rgb[0], green=rgb[1], blue=rgb[2])
        return fore
         
class TextPrintout(wx.lib.docview.DocPrintout):
    """ for Print Preview and Print """
    

    def OnPreparePrinting(self):
        """ initialization """
        dc = self.GetDC()

        ppiScreenX, ppiScreenY = self.GetPPIScreen()
        ppiPrinterX, ppiPrinterY = self.GetPPIPrinter()
        scaleX = float(ppiPrinterX)/ppiScreenX
        scaleY = float(ppiPrinterY)/ppiScreenY

        pageWidth, pageHeight = self.GetPageSizePixels()
        self._scaleFactorX = scaleX/pageWidth
        self._scaleFactorY = scaleY/pageHeight

        w, h = dc.GetSize()
        overallScaleX = self._scaleFactorX * w
        overallScaleY = self._scaleFactorY * h
        
        txtCtrl = self._printoutView.GetCtrl()
        font, color = txtCtrl.GetFontAndColorFromConfig()

        self._margin = 40
        self._fontHeight = font.GetPointSize() + 1
        self._pageLines = int((h/overallScaleY - (2 * self._margin))/self._fontHeight)
        self._maxLines = txtCtrl.GetLineCount()
        self._numPages, remainder = divmod(self._maxLines, self._pageLines)
        if remainder != 0:
            self._numPages += 1

        spaces = 1
        lineNum = self._maxLines
        while lineNum >= 10:
            lineNum = lineNum/10
            spaces += 1
        self._printFormat = "%%0%sd: %%s" % spaces


    def OnPrintPage(self, page):
        """ Prints the given page of the view """
        dc = self.GetDC()
        
        txtCtrl = self._printoutView.GetCtrl()
        font, color = txtCtrl.GetFontAndColorFromConfig()
        dc.SetFont(font)
        
        w, h = dc.GetSize()
        dc.SetUserScale(self._scaleFactorX * w, self._scaleFactorY * h)
        
        dc.BeginDrawing()
        
        dc.DrawText("%s - page %s" % (self.GetTitle(), page), self._margin, self._margin/2)

        startY = self._margin
        startLine = (page - 1) * self._pageLines
        endLine = min((startLine + self._pageLines), self._maxLines)
        for i in range(startLine, endLine):
            text = txtCtrl.GetLine(i).rstrip()
            startY += self._fontHeight
            if txtCtrl.GetViewLineNumbers():
                dc.DrawText(self._printFormat % (i+1, text), self._margin, startY)
            else:
                dc.DrawText(text, self._margin, startY)
                
        dc.EndDrawing()

        return True


    def HasPage(self, pageNum):
        return pageNum <= self._numPages


    def GetPageInfo(self):
        minPage = 1
        maxPage = self._numPages
        selPageFrom = 1
        selPageTo = self._numPages
        return (minPage, maxPage, selPageFrom, selPageTo)

        
#----------------------------------------------------------------------------
# Icon Bitmaps - generated by encode_bitmaps.py
#----------------------------------------------------------------------------
from wx import ImageFromStream, BitmapFromImage
import cStringIO

def getTextBitmap():
    blank_image_path = os.path.join(sysutilslib.mainModuleDir, "noval", "tool", "bmp_source", "file.gif")
    blank_image = wx.Image(blank_image_path,wx.BITMAP_TYPE_ANY)
    return BitmapFromImage(blank_image)

def getTextIcon():
    return wx.IconFromBitmap(getTextBitmap())




