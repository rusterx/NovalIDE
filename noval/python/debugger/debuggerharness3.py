#----------------------------------------------------------------------------
# Name:         DebuggerHarness.py
# Purpose:      
#
# Author:       Matt Fryer
#
# Created:      7/28/04
# CVS-ID:       $Id$
# Copyright:    (c) 2005 ActiveGrid, Inc.
# License:      wxWindows License
#----------------------------------------------------------------------------
import bdb
import sys
import threading
import os
import types
import traceback
import inspect
from xml.dom.minidom import getDOMImplementation
import atexit
import pickle
import bz2
from xmlrpc.server import SimpleXMLRPCServer
import xmlrpc.client as xmlrpclib
import queue as Queue
import io as cStringIO
import importlib

_lock = threading.Lock()

if sys.platform.startswith("win"):
    ####import win32api
    _WINDOWS = True
else:
    _WINDOWS = False
    
_VERBOSE = False
_DEBUG_DEBUGGER = False
DEBUG_UNKNOWN_VALUE_TYPE = 'Unknown'
class BaseStdIn:
    
    def readline(self, *args, **kwargs):
        #sys.stderr.write('Cannot readline out of the console evaluation\n') -- don't show anything
        #This could happen if the user had done input('enter number).<-- upon entering this, that message would appear,
        #which is not something we want.
        return '\n'
    
    def isatty(self):    
        return False #not really a file
        
    def write(self, *args, **kwargs):
        pass #not available StdIn (but it can be expected to be in the stream interface)
        
    def flush(self, *args, **kwargs):
        pass #not available StdIn (but it can be expected to be in the stream interface)
       
    def read(self, *args, **kwargs):
        #in the interactive interpreter, a read and a readline are the same.
        return self.readline()
    
#=======================================================================================================================
# StdIn
#=======================================================================================================================
class StdIn(BaseStdIn):
    '''
        Object to be added to stdin (to emulate it as non-blocking while the next line arrives)
    '''
    
    def __init__(self, host, client_port):
        self.client_port = client_port
        self.host = host
    
    def readline(self, *args, **kwargs):
        #Ok, callback into the client to see get the new input
        server = xmlrpclib.Server('http://%s:%s' % (self.host, self.client_port))
        
        requested_input = server.request_input()
        if not requested_input and requested_input!='':
            raise KeyboardInterrupt("operation cancelled")
        
        if requested_input=='':
            return '\n'  #Yes, a readline must return something (otherwise we can get an EOFError on the input() call).
        
        return requested_input

class Adb(bdb.Bdb):

    def __init__(self, harness, queue):
        bdb.Bdb.__init__(self)
        self._harness = harness
        self._userBreak = False
        self._queue = queue
        self._knownCantExpandFiles = {} 
        self._knownExpandedFiles = {} 
        self._exceptions = []
    
    def getLongName(self, filename):
        if not _WINDOWS:
            return filename
        if self._knownCantExpandFiles.get(filename):
            return filename
        if self._knownExpandedFiles.get(filename):
            return self._knownExpandedFiles.get(filename)
        try:
            newname = win32api.GetLongPathName(filename)
            self._knownExpandedFiles[filename] = newname
            return newname
        except:
            self._knownCantExpandFiles[filename] = filename
            return filename
            
    def canonic(self, orig_filename):
        if orig_filename == "<" + orig_filename[1:-1] + ">":
            return orig_filename
        filename = self.getLongName(orig_filename)    

        canonic = self.fncache.get(filename)
        if not canonic:
            canonic = os.path.abspath(filename)
            canonic = os.path.normcase(canonic)
            self.fncache[filename] = canonic
        return canonic
    
     
    # Overriding this so that we continue to trace even if no breakpoints are set.
    def set_continue(self):
        self.stopframe = self.botframe
        self.returnframe = None
        self.quitting = 0  
                         
    def do_clear(self, arg):
        bdb.Breakpoint.bpbynumber[int(arg)].deleteMe()
        
    def user_line(self, frame):
        if self.in_debugger_code(frame):
            self.set_step()
            return
        message = self.__frame2message(frame)
        self._harness.interaction(message, frame, "")
        
    def user_call(self, frame, argument_list):
        if self.in_debugger_code(frame):
            self.set_step()
            return
        if self.stop_here(frame):
            message = self.__frame2message(frame)
            self._harness.interaction(message, frame, "")
        
    def user_return(self, frame, return_value):
        if self.in_debugger_code(frame):
            self.set_step()
            return
        message = self.__frame2message(frame)
        self._harness.interaction(message, frame, "")
        
    def user_exception(self, frame,exc_info):
        exc_type, exc_value, exc_traceback = exc_info
        frame.f_locals['__exception__'] = exc_type, exc_value
        if type(exc_type) == type(''):
            exc_type_name = exc_type
        else: 
            exc_type_name = exc_type.__name__
        message = "Exception occured: " + repr(exc_type_name) + " See locals.__exception__ for details."
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        self._harness.interaction(message, frame, message)

    def in_debugger_code(self, frame):
        if _DEBUG_DEBUGGER: return False
        message = self.__frame2message(frame)
        return message.count('DebuggerHarness') > 0
        
    def frame2message(self, frame):
        return self.__frame2message(frame)
        
    def __frame2message(self, frame):
        code = frame.f_code
        filename = code.co_filename
        lineno = frame.f_lineno
        basename = os.path.basename(filename)
        message = "%s:%s" % (basename, lineno)
        if code.co_name != "?":
            message = "%s: %s()" % (message, code.co_name)
        return message
        
    def runFile(self, fileName):
        self.reset()
        #global_dict = {}
        #global_dict['__name__'] = '__main__'
        try:
            fileToRun = open(fileName, mode='r',encoding="utf-8")
            code_obj = compile(fileToRun.read(),fileName,mode='exec')
            if _VERBOSE: print ("Running file ", fileName)
            sys.settrace(self.trace_dispatch)
            import __main__
            exec (code_obj,__main__.__dict__,__main__.__dict__)
            fileToRun.close()
        except SystemExit:
            pass
        except:
            tp, val, tb = sys.exc_info()
            traceback.print_exception(tp, val, tb)
           
        sys.settrace(None)
        self.quitting = 1
        #global_dict.clear()
 
    def trace_dispatch(self, frame, event, arg):
        if self.quitting:
            return # None
        # Check for ui events
        self.readQueue()
        if event == 'line':
            return self.dispatch_line(frame)
        if event == 'call':
            return self.dispatch_call(frame, arg)
        if event == 'return':
            return self.dispatch_return(frame, arg)
        if event == 'exception':
            if arg[0].__name__ in self._exceptions:
                self._userBreak = True
            return self.dispatch_exception(frame, arg)
        print ('Adb.dispatch: unknown debugging event:', event)
        return self.trace_dispatch
     
    def readQueue(self):
        while self._queue.qsize():
            try:
                item = self._queue.get_nowait()
                if item.kill():
                    self._harness.do_exit(kill=True)
                elif item.breakHere():
                    self._userBreak = True
                elif item.hasBreakpoints():
                    self.set_all_breakpoints(item.getBreakpoints())
            except Queue.Empty:
                pass
                                  
    def set_all_breakpoints(self, dict):
        self.clear_all_breaks()
        for fileName in dict.keys():
            lineList = dict[fileName]
            for lineNumber in lineList:
                if _VERBOSE:
                    print ("Setting break at line ", str(lineNumber), " in file ", self.canonic(fileName))
                self.set_break(fileName, int(lineNumber))
        return ""
                
    def stop_here(self, frame):
        if self._userBreak:
            return True
        

        # (CT) stopframe may now also be None, see dispatch_call.
        # (CT) the former test for None is therefore removed from here.
        if frame is self.stopframe:
            return True
        while frame is not None and frame is not self.stopframe:
            if frame is self.botframe:
                return True
            frame = frame.f_back
        return False
        
    def clear_exception(self):
        self._exceptions = []
        
    def set_exception(self,exception):
        if exception in self._exceptions:
            return
        self._exceptions.append(exception)

class BreakNotify(object):
    def __init__(self, bps=None, break_here=False, kill=False):
        self._bps = bps
        self._break_here = break_here
        self._kill = kill
        
    def breakHere(self):
        return self._break_here
        
    def kill(self):
        return self._kill
        
    def getBreakpoints(self):
        return self._bps
    
    def hasBreakpoints(self):
        return (self._bps != None)

class AGXMLRPCServer(SimpleXMLRPCServer):
    def __init__(self, address, logRequests=0):
        SimpleXMLRPCServer.__init__(self, address, logRequests=logRequests)               
        
class BreakListenerThread(threading.Thread):
    def __init__(self, host, port, queue):
        threading.Thread.__init__(self)
        self._host = host
        self._port = int(port)
        self._keepGoing = True
        self._queue = queue
        self._server = AGXMLRPCServer((self._host, self._port), logRequests=0)
        self._server.register_function(self.update_breakpoints)
        self._server.register_function(self.break_requested)
        self._server.register_function(self.die)
    
    def break_requested(self):
        bn = BreakNotify(break_here=True)
        self._queue.put(bn)
        return ""
        
    def update_breakpoints(self, pickled_Binary_bpts):
        dict = pickle.loads(pickled_Binary_bpts.data)
        bn = BreakNotify(bps=dict)
        self._queue.put(bn)
        return ""
        
    def die(self):
        bn = BreakNotify(kill=True)
        self._queue.put(bn)
        return ""
            
    def run(self):
        while self._keepGoing:
            try:
                self._server.handle_request() 
            except:
                if _VERBOSE:
                    tp, val, tb = sys.exc_info()
                    print ("Exception in BreakListenerThread.run():", str(tp), str(val))
                self._keepGoing = False
       
    def AskToStop(self):
        self._keepGoing = False
        if self._server is None:
            if _VERBOSE:
                print ("Before calling server close on breakpoint server")
            self._server.server_close()
            if _VERBOSE:
                print ("Calling server close on breakpoint server")
            self._server = None
                           
        
class DebuggerHarness(object):
    
    def __init__(self):
        # Host and port for debugger-side RPC server
        self._hostname = sys.argv[1]
        self._portNumber = int(sys.argv[2])
        # Name the gui proxy object is registered under
        self._breakPortNumber = int(sys.argv[3])
        # Host and port where the gui proxy can be found.
        self._guiHost = sys.argv[4]
        self._guiPort = int(sys.argv[5])
        # Command to debug.
        self._command = sys.argv[6]
        # Strip out the harness' arguments so that the process we run will see argv as if
        # it was called directly.
        sys.argv = sys.argv[6:]
        self._currentFrame = None
        self._wait = False
        # Connect to the gui-side RPC server.
        self._guiServerUrl = 'http://' + self._guiHost + ':' + str(self._guiPort) + '/'
        if _VERBOSE:
            print ("Connecting to gui server at ", self._guiServerUrl)
        self._guiServer = xmlrpclib.ServerProxy(self._guiServerUrl,allow_none=1)
    
        #redirect std input 
        sys.stdin = StdIn( self._guiHost, self._guiPort)
        # Start the break listener
        self._breakQueue = Queue.Queue(50)
        self._breakListener = BreakListenerThread(self._hostname, self._breakPortNumber, self._breakQueue)        
        self._breakListener.start()
        # Create the debugger.
        self._adb = Adb(self, self._breakQueue)
        
        # Create the debugger-side RPC Server and register functions for remote calls.
        self._server = AGXMLRPCServer((self._hostname, self._portNumber), logRequests=0)
        self._server.register_function(self.set_step)
        self._server.register_function(self.set_continue)
        self._server.register_function(self.set_next)
        self._server.register_function(self.set_return)
        self._server.register_function(self.set_breakpoint)
        self._server.register_function(self.set_all_exceptions)
        self._server.register_function(self.clear_breakpoint)
        self._server.register_function(self.set_all_breakpoints)
        self._server.register_function(self.attempt_introspection)
        self._server.register_function(self.execute_in_frame)
        self._server.register_function(self.add_watch)
        self._server.register_function(self.request_frame_document)
        
        self.frame_stack = []
        self.message_frame_dict = {}
        self.introspection_list = []
        atexit.register(self.do_exit)
        
    def run(self):
        self._adb.runFile(self._command)
        self.do_exit(kill=True)

        
    def do_exit(self, kill=False):
        self._adb.set_quit()
        self._breakListener.AskToStop()
        self._server.server_close()
        try:
            self._guiServer.quit()
        except:
            pass
        if kill:
            try:
                sys.exit()
            except:
                pass
        
    def set_breakpoint(self, fileName, lineNo):
        self._adb.set_break(fileName, lineNo)
        return ""
        
    def set_all_exceptions(self,exceptions):
        self._adb.clear_exception()
        for exception in exceptions:
            self._adb.set_exception(exception)
        return ""
        
    def set_all_breakpoints(self, dict):
        self._adb.clear_all_breaks()
        for fileName in dict.keys():
            lineList = dict[fileName]
            for lineNumber in lineList:
                self._adb.set_break(fileName, int(lineNumber))
                if _VERBOSE:
                    print ("Setting break at ", str(lineNumber), " in file ", fileName)
        return ""
                                        
    def clear_breakpoint(self, fileName, lineNo):
        self._adb.clear_break(fileName, lineNo)
        return ""

    def add_watch(self,  name,  text, frame_message, run_once):
        with _lock:
            if len(frame_message) > 0:
                frame = self.message_frame_dict[frame_message] 
                try:
                    item = eval(text, frame.f_globals, frame.f_locals)
                    return self.get_watch_document(item, name)
                except: 
                    tp, val, tb = sys.exc_info()
                    return self.get_exception_document(name,tp, val, tb) 
            return ""
        
    def execute_in_frame(self, frame_message, command):
        frame = self.message_frame_dict[frame_message]
        output = cStringIO.StringIO()
        out = sys.stdout
        err = sys.stderr
        sys.stdout = output
        sys.stderr = output
        try:
            code = compile(command, '<string>', 'single')
            exec(code,frame.f_locals,frame.f_globals)
            return output.getvalue()
            sys.stdout = out
            sys.stderr = err        
        except:
            sys.stdout = out
            sys.stderr = err        

            tp, val, tb = sys.exc_info()           
            output = cStringIO.StringIO()
            traceback.print_exception(tp, val, tb, file=output)
            return output.getvalue()   
               
    def attempt_introspection(self, frame_message, chain):
        
        def get_item(source_item,name,chain):
            item = source_item
            for name in chain:
                item = self.getNextItem(item, name)
            return item,name
        try:
            frame = self.message_frame_dict[frame_message]
            if frame:
                name = chain[0]
                if name == 'globals':
                    chain.pop(0)
                    items = [frame.f_globals]
                elif name == 'locals':
                    chain.pop(0)
                    items = [frame.f_locals]
                else:
                    items = [frame.f_globals,frame.f_locals]
                if 1 == len(items):
                    item,name = get_item(items[0],name,chain)
                else:
                    item = None
                    source_name = name
                    for source_item in items:
                        value,item_name = get_item(source_item,source_name,chain)
                        if value is not None:
                            item = value
                        name = item_name
                return self.get_introspection_document(item, name)
        except:
            tp, val, tb = sys.exc_info()
            traceback.print_exception(tp, val, tb)
        return self.get_empty_introspection_document()   
        
    def getNextItem(self, link, identifier):
        tp = type(link)
        if self.isTupleized(identifier):
            return self.deTupleize(link, identifier)
        else:
            if tp is dict or tp == types.MappingProxyType:
                return link.get(identifier,None)
            else:
                if hasattr(link, identifier):
                    return getattr(link, identifier)
            if _VERBOSE or True:
                print ("Failed to find link ", identifier, " on thing: ", self.saferepr(link), " of type ", repr(type(link)))
            return None
        
    def isPrimitive(self, item):
        tp = type(item)
        return tp is types.IntType or tp is types.LongType or tp is types.FloatType \
            or tp is types.BooleanType or tp is types.ComplexType \
            or tp is types.StringType  
    
    def isTupleized(self, value):
        return value.count('[')
                             
    def deTupleize(self, link, string1):
        try:
            start = string1.find('[')
            end = string1.find(']')
            num = int(string1[start+1:end])
            return link[num]
        except:
            tp,val,tb = sys.exc_info()
            if _VERBOSE: 
                print ("Got exception in deTupleize: ", val)
            return None
                        
    def wrapAndCompress(self, stringDoc):
        import bz2
        return xmlrpclib.Binary(bz2.compress(stringDoc.encode()))

    def get_empty_introspection_document(self):
        doc = getDOMImplementation().createDocument(None, "replacement", None)
        return self.wrapAndCompress(doc.toxml())

    def get_watch_document(self, item, identifier):   
        doc = getDOMImplementation().createDocument(None, "watch", None)
        top_element = doc.documentElement
        self.addAny(top_element, identifier, item, doc, 2)
        return self.wrapAndCompress(doc.toxml())
        
    def get_introspection_document(self, item, identifier):   
        doc = getDOMImplementation().createDocument(None, "replacement", None)
        top_element = doc.documentElement
        self.addAny(top_element, identifier, item, doc, 2)
        return self.wrapAndCompress(doc.toxml())
   
    def get_exception_document(self, name, tp, val, tb):                  
        stack = traceback.format_exception(tp, val, tb)
        wholeStack = ""
        for line in stack:
            wholeStack += line
        doc = getDOMImplementation().createDocument(None, "watch", None)
        top_element = doc.documentElement
        item_node = doc.createElement("dict_nv_element")  
        item_node.setAttribute('value', wholeStack)
        item_node.setAttribute('type', DEBUG_UNKNOWN_VALUE_TYPE)
        item_node.setAttribute('name', str(name))    
        top_element.appendChild(item_node)
        return self.wrapAndCompress(doc.toxml())
        
    cantIntro = [types.FunctionType, 
             types.LambdaType,
             str,
             None,
             int,
             float,
             bool]     
     
    def addAny(self, top_element, name, item, doc, ply):
        tp = type(item)
        
        if tp in DebuggerHarness.cantIntro or ply < 1:
            self.addNode(top_element,name, item, doc)
        elif tp is tuple or tp is list:
            self.addTupleOrList(top_element, name, item, doc, ply - 1)           
        elif tp is dict or tp is types.MappingProxyType: 
            self.addDict(top_element, name, item, doc, ply -1)
        elif inspect.ismodule(item): 
            self.addModule(top_element, name, item, doc, ply -1)
        elif inspect.isclass(item) or inspect.isclass(item.__class__):
            self.addClass(top_element, name, item, doc, ply -1)
        elif hasattr(item, '__dict__'):
            self.addDictAttr(top_element, name, item, doc, ply -1)
        else:
            self.addNode(top_element,name, item, doc) 

            
    def canIntrospect(self, item):
        tp = type(item)
        if tp in DebuggerHarness.cantIntro:
            return False
        elif tp is tuple or tp is list:
            return len(item) > 0          
        elif tp is dict or tp is types.MappingProxyType: 
            return len(item) > 0
        elif inspect.ismodule(item): 
            return True
        elif inspect.isclass(item) or inspect.isclass(item.__class__):
            if hasattr(item, '__dict__'):
                return True
            elif hasattr(item, '__name__'):
                return True
            elif hasattr(item, '__module__'):
                return True
            elif hasattr(item, '__doc__'):
                return True
            else:
                return False
        elif hasattr(item, '__dict__'):
            return len(item.__dict__) > 0
        else:
            return False

    def addNode(self, parent_node, name, item, document):
        item_node = document.createElement("dict_nv_element")  
        value,value_type = self.saferepr(item)
        item_node.setAttribute('value',value)
        item_node.setAttribute('type',value_type)
        item_node.setAttribute('name', str(name))    
        introVal = str(self.canIntrospect(item))
        item_node.setAttribute('intro', str(introVal))
        parent_node.appendChild(item_node)
             
    def addTupleOrList(self, top_node, name, tupple, doc, ply):
        tupleNode = doc.createElement('tuple')
        tupleNode.setAttribute('name', str(name))
        value,value_type = self.saferepr(tupple)
        tupleNode.setAttribute('value',value)
        tupleNode.setAttribute('type',value_type)
        top_node.appendChild(tupleNode)
        count = 0
        for item in tupple:
            self.addAny(tupleNode, name +'[' + str(count) + ']',item, doc, ply -1)
            count += 1
            
    def addDictAttr(self, root_node, name, thing, document, ply):
        dict_node = document.createElement('thing') 
        dict_node.setAttribute('name', name)
        value,value_type = self.saferepr(thing)
        dict_node.setAttribute('value',value)
        dict_node.setAttribute('type',value_type)
        root_node.appendChild(dict_node)
        self.addDict(dict_node, '', thing.__dict__, document, ply) # Not decreminting ply
            
    def addDict(self, root_node, name, dict, document, ply):
        if name != '':
            dict_node = document.createElement('dict') 
            dict_node.setAttribute('name', name)
            value,value_type = self.saferepr(dict)
            dict_node.setAttribute('value',value)
            dict_node.setAttribute('type',value_type)
            root_node.appendChild(dict_node)
        else:
            dict_node = root_node
        for key in dict.keys():
            strkey = str(key)
            try:
                value = dict[key]
                self.addAny(dict_node, strkey, value, document, ply-1)
            except:
                if _VERBOSE:
                    tp,val,tb=sys.exc_info()
                    print ("Error recovering key: ", str(key), " from node ", str(name), " Val = ", str(val))
                    traceback.print_exception(tp, val, tb)
                    
    def addClass(self, root_node, name, class_item, document, ply):
         item_node = document.createElement('class') 
         item_node.setAttribute('name', str(name)) 
         value,value_type = self.saferepr(class_item)
         item_node.setAttribute('value',value)
         item_node.setAttribute('type',value_type)
         root_node.appendChild(item_node)
         try:
             if hasattr(class_item, '__dict__'):
                self.addDict(item_node, '', class_item.__dict__, document, ply -1)
         except:
             tp,val,tb=sys.exc_info()
             if _VERBOSE:
                traceback.print_exception(tp, val, tb)
         try:
             if hasattr(class_item, '__name__'):
                self.addAny(item_node,'__name__',class_item.__name__, document, ply -1)
         except:
             tp,val,tb=sys.exc_info()
             if _VERBOSE:
                traceback.print_exception(tp, val, tb)
         try:
             if hasattr(class_item, '__module__'):
                self.addAny(item_node, '__module__', class_item.__module__, document, ply -1)
         except:
             tp,val,tb=sys.exc_info()
             if _VERBOSE:
                traceback.print_exception(tp, val, tb)
         try:
             if hasattr(class_item, '__doc__'):
                self.addAny(item_node, '__doc__', class_item.__doc__, document, ply -1)
         except:
             tp,val,tb=sys.exc_info()
             if _VERBOSE:
                traceback.print_exception(tp, val, tb)
         try:
             if hasattr(class_item, '__bases__'):
                self.addAny(item_node, '__bases__', class_item.__bases__, document, ply -1)
         except:
             tp,val,tb=sys.exc_info()
             if _VERBOSE:
                traceback.print_exception(tp, val, tb)
         
    def addModule(self, root_node, name, module_item, document, ply):
         item_node = document.createElement('module') 
         item_node.setAttribute('name', str(name))
         value,value_type = self.saferepr(module_item)
         item_node.setAttribute('value',value)
         item_node.setAttribute('type',value_type)
         root_node.appendChild(item_node)
         try:
             if hasattr(module_item, '__file__'):
                self.addAny(item_node, '__file__', module_item.__file__, document, ply -1)
         except:
             pass
         try:
             if hasattr(module_item, '__doc__'):
                self.addAny(item_node,'__doc__', module_item.__doc__, document, ply -1)
         except:
             pass
                   
            
        
    def getFrameXML(self, base_frame):

        self.frame_stack = []
        frame = base_frame
        while frame is not None:
            if((frame.f_code.co_filename.count('debuggerharness3.py') == 0) or _DEBUG_DEBUGGER):
                self.frame_stack.append(frame)
            frame = frame.f_back
        self.frame_stack.reverse()
        self.message_frame_dict = {}
        doc = getDOMImplementation().createDocument(None, "stack", None)
        top_element = doc.documentElement
        numberFrames = len(self.frame_stack)
        for index in range(numberFrames):
            frame = self.frame_stack[index]
            message = self._adb.frame2message(frame)
            # We include globals and locals only for the last frame as an optimization for cases
            # where there are a lot of frames.
            self.addFrame(frame, top_element, doc, includeContent=(index == numberFrames - 1))
        return doc.toxml()
        
    def addFrame(self, frame, root_element, document, includeContent=False):
        frameNode = document.createElement('frame')
        root_element.appendChild(frameNode)
        
        code = frame.f_code
        filename = code.co_filename
        if str(filename) == "<frozen importlib._bootstrap>":
            filename = importlib._bootstrap.__file__
            
        if str(filename) == "<frozen importlib._bootstrap_external>":
            filename = importlib._bootstrap_external.__file__
        frameNode.setAttribute('file', str(filename))    
        frameNode.setAttribute('line', str(frame.f_lineno))
        message = self._adb.frame2message(frame)
        frameNode.setAttribute('message', message)
        self.message_frame_dict[message] = frame
        if includeContent:
            self.addDict(frameNode, "locals", frame.f_locals, document, 2)        
            self.addNode(frameNode, "globals", frame.f_globals,  document)
            
    def request_frame_document(self, message):
        frame = self.message_frame_dict[message]  
        doc = getDOMImplementation().createDocument(None, "stack", None)
        top_element = doc.documentElement
        if frame:
            self.addFrame(frame, top_element, doc, includeContent=True)
        return xmlrpclib.Binary(bz2.compress(doc.toxml().encode()))
            
    def getRepr(self, varName, globals, locals):
        try:
            return repr(eval(varName, globals, locals))
        except:
            return 'Error: Could not recover value.'
            
   
    def saferepr(self, thing):
        try:
            value_type = str(type(thing))
            try:
                return repr(thing),value_type
            except:
                return value_type,value_type
        except:
            tp, val, tb = sys.exc_info()
            #traceback.print_exception(tp, val, tb)
            return repr(val),DEBUG_UNKNOWN_VALUE_TYPE
                    
    # The debugger calls this method when it reaches a breakpoint.
    def interaction(self, message, frame, info):
        if _VERBOSE:
            print ('hit debug side interaction')
        self._adb._userBreak = False

        self._currentFrame = frame
        done = False
        while not done:
            try:
                xml = self.getFrameXML(frame)
                arg = xmlrpclib.Binary(bz2.compress(xml.encode('utf-8')))
                if _VERBOSE:
                    print ('============== calling gui side interaction============')
                self._guiServer.interaction(xmlrpclib.Binary(message.encode('utf-8')), arg, info)
                if _VERBOSE:
                    print ('after interaction')
                done = True
            except:
                tp, val, tb = sys.exc_info()
                if True or _VERBOSE:
                    print ('Error contacting GUI server!: ')
                    try:
                        traceback.print_exception(tp, val, tb)
                    except:
                        print ("Exception printing traceback"), 
                        tp, val, tb = sys.exc_info()
                        traceback.print_exception(tp, val, tb)
                done = False
        # Block while waiting to be called back from the GUI. Eventually, self._wait will
        # be set false by a function on this side. Seems pretty lame--I'm surprised it works.
        self.waitForRPC()
        

    def waitForRPC(self):
        self._wait = True
        while self._wait :
            try:
                if _VERBOSE:
                    print ("+++ in harness wait for rpc, before handle_request")
                self._server.handle_request()
                if _VERBOSE:
                    print ("+++ in harness wait for rpc, after handle_request")
            except:
                if _VERBOSE:
                    tp, val, tb = sys.exc_info()
                    print ("Got waitForRpc exception : ", repr(tp), ": ", val)
            #time.sleep(0.1)
    
    def set_step(self):
        self._adb.set_step()
        self._wait = False
        return ""
        
    def set_continue(self):
        self._adb.set_continue()
        self._wait = False
        return ""
        
    def set_next(self):
        self._adb.set_next(self._currentFrame)
        self._wait = False
        return ""
        
    def set_return(self):
        self._adb.set_return(self._currentFrame)
        self._wait = False
        return ""        
     
if __name__ == '__main__':
    try:
        harness = DebuggerHarness()
        harness.run()
        harness.do_exit(kill=True)
    except SystemExit:
        print ("Exiting...")
    except:
        tp, val, tb = sys.exc_info()
        traceback.print_exception(tp, val, tb)
