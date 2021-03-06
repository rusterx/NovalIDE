# -- coding: utf-8 --
#-------------------------------------------------------------------------------
# Name:        _xml.py
# Purpose:
#
# Author:      wukan
#
# Created:     2019-01-17
# Copyright:   (c) wukan 2019
# Licence:     <your licence>
#-------------------------------------------------------------------------------

#-----------------------------------------------------------------------------#
from noval import _
from noval.syntax import syndata,lang
from noval.syntax.pat import *
import noval.util.appdirs as appdirs
import os
import noval.editor.code as codeeditor
import noval.imageutils as imageutils
#-----------------------------------------------------------------------------#
#-----------------------------------------------------------------------------#
def make_pat(is_html=False):
    cregx = stringprefix + r"<!--((?!(-->)).)*(-->)?"
    comment = matches_any("comment", [cregx])
    xml_tag = matches_any("stderr",[r"<\w+>",r"</\w+>",r'(?<=<\?)xml',\
                    r'<\w+\s+',r'/>',r'(?<=")>',r'<\w+/>'])
    attr = matches_any("builtin",[r'\b\w+(?==")'])
    if is_html:
        declaration = matches_any("value",[r'<!',r'(?<=html)>'])
    else:
        declaration = matches_any("value",[r'<\?',r'\?>'])
    dqstring = get_dqstring_pat()
    string = matches_any("string", [dqstring])
    return comment + "|" + xml_tag + "|" + attr + "|" + declaration + "|"+ string +\
           "|" + matches_any("SYNC", [r"\n"])

prog = get_prog(make_pat())

#-----------------------------------------------------------------------------#

class SyntaxColorer(syndata.BaseSyntaxcolorer):
    def __init__(self, text):
        syndata.BaseSyntaxcolorer.__init__(self,text)
        self.prog = prog
        self._config_tags()

    def _config_tags(self):
        self.tagdefs.update({
        "stdin",
        'stderr',
        })
        
class SyntaxLexer(syndata.BaseLexer):
    """SyntaxData object for Python"""        
    def __init__(self):
        lang_id = lang.RegisterNewLangId("ID_LANG_XML")
        syndata.BaseLexer.__init__(self,lang_id)
        
    def GetDescription(self):
        return _('XML File')
        
    def GetExt(self):
        return "axl dtd plist rdf svg xml xrc xsd xsl xslt xul"

    def GetDefaultCommentPattern(self):
        """Returns a list of characters used to comment a block of code """
        return [u'<!--', u'-->']

    def GetShowName(self):
        return "XML"
        
    def GetDefaultExt(self):
        return "xml"
        
    def GetDocTypeName(self):
        return "XML Document"
        
    def GetViewTypeName(self):
        return _("XML Editor")
        
    def GetDocTypeClass(self):
        return codeeditor.CodeDocument
        
    def GetViewTypeClass(self):
        return codeeditor.CodeView
        
    def GetDocIcon(self):
        return imageutils.load_image("","file/xml.png")
        
    def GetSampleCode(self):
        sample_file_path = os.path.join(appdirs.get_app_data_location(),"sample","xml.sample")
        return self.GetSampleCodeFromFile(sample_file_path)
        
    def GetColorClass(self):
        return SyntaxColorer
