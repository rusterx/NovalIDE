# -*- coding: utf-8 -*-

"""Code for maintaining the background process and for running
user programs

Commands get executed via shell, this way the command line in the 
shell becomes kind of title for the execution.

"""
from noval import GetApp
import collections
import os.path
import shlex
import shutil
import signal
import subprocess
import sys
import time
import traceback
from threading import Thread
from time import sleep
from noval.util import utils
import noval.util.strutils as strutils
import noval.python.pyutils as pyutils
from noval.util.command import *


OUTPUT_MERGE_THRESHOLD = 1000

RUN_COMMAND_LABEL = ""
RUN_COMMAND_CAPTION = ""
EDITOR_CONTENT_TOKEN = "$EDITOR_CONTENT"

EXPECTED_TERMINATION_CODE = 1234

# other components may turn it on in order to avoid grouping output lines into one event
io_animation_required = False


class Runner:
    def __init__(self,shell_view):
      #  get_workbench().set_default("run.auto_cd", True)
        self._init_commands()
        self._state = "starting"
        self._proxy = None  # type: Any
        self._publishing_events = False
        self._polling_after_id = None
        self._postponed_commands = []  # type: List[CommandToBackend]
        self.shell_view = shell_view

    def _remove_obsolete_jedi_copies(self):
        # Thonny 2.1 used to copy jedi in order to make it available
        # for the backend. Get rid of it now
        for item in os.listdir(THONNY_USER_DIR):
            if item.startswith("jedi_0."):
                shutil.rmtree(os.path.join(THONNY_USER_DIR, item), True)

    def start(self):
        self._check_alloc_console()
        self.restart_backend(False, True)

    def _init_commands(self):
        pass

    def get_state(self):
        """State is one of "running", "waiting_debugger_command", "waiting_toplevel_command"
        """
        return self._state

    def _set_state(self, state):
        if self._state != state:
            utils.get_logger().debug("Runner state changed: %s ==> %s" % (self._state, state))
            self._state = state

    def is_running(self):
        return self._state == "running" and self._proxy is not None

    def is_waiting(self):
        return self._state.startswith("waiting")

    def is_waiting_toplevel_command(self):
        return self._state == "waiting_toplevel_command"

    def is_waiting_debugger_command(self):
        return self._state == "waiting_debugger_command"

    def send_command(self, cmd):
        if self._proxy is None:
            return

        if self._publishing_events:
            # allow all event handlers to complete before sending the commands
            # issued by first event handlers
            self._postpone_command(cmd)
            return

        # First sanity check
        if (
            isinstance(cmd, ToplevelCommand)
            and not self.is_waiting_toplevel_command()
            and cmd.name not in ["Reset", "Run", "Debug"]
            or isinstance(cmd, DebuggerCommand)
            and not self.is_waiting_debugger_command()
        ):
            get_workbench().bell()
            utils.get_logger().warning(
                "RUNNER: Command %s was attempted at state %s" % (cmd, self.get_state())
            )
            return

        # Attach extra info
        if "debug" in cmd.name.lower():
            cmd["breakpoints"] = get_current_breakpoints()

        # Offer the command
        utils.get_logger().debug("RUNNER Sending: %s, %s", cmd.name, cmd)
        response = self._proxy.send_command(cmd)

        if response == "discard":
            return
        elif response == "postpone":
            self._postpone_command(cmd)
            return
        else:
            assert response is None
            GetApp().event_generate("CommandAccepted", command=cmd)

        if isinstance(cmd, (ToplevelCommand, DebuggerCommand)):
            self._set_state("running")

        if cmd.name[0].isupper():
            GetApp().event_generate("BackendRestart", full=False)

    def _postpone_command(self, cmd):
        # in case of InlineCommands, discard older same type command
        if isinstance(cmd, InlineCommand):
            for older_cmd in self._postponed_commands:
                if older_cmd.name == cmd.name:
                    self._postponed_commands.remove(older_cmd)

        if len(self._postponed_commands) > 10:
            utils.get_logger().warning("Can't pile up too many commands. This command will be just ignored")
        else:
            self._postponed_commands.append(cmd)

    def _send_postponed_commands(self):
        todo = self._postponed_commands
        self._postponed_commands = []

        for cmd in todo:
            utils.get_logger().debug("Sending postponed command: %s", cmd)
            self.send_command(cmd)

    def send_program_input(self, data):
        assert self.is_running()
        self._proxy.send_program_input(data)

    def _get_active_arguments(self):
        if get_workbench().get_option("view.show_program_arguments"):
            args_str = get_workbench().get_option("run.program_arguments")
            get_workbench().log_program_arguments_string(args_str)
            return shlex.split(args_str)
        else:
            return []

    def _cmd_interrupt(self):
        if self._proxy is not None:
            self._proxy.interrupt()
        else:
            utils.get_logger().warning("Interrupting without proxy")

    def _cmd_interrupt_enabled(self):
        if not self._proxy or not self._proxy.is_functional():
            return False
        # TODO: distinguish command and Ctrl+C shortcut

        widget = get_workbench().focus_get()
        if not running_on_mac_os():  # on Mac Ctrl+C is not used for Copy
            if widget is not None and hasattr(widget, "selection_get"):
                try:
                    selection = widget.selection_get()
                    if isinstance(selection, str) and len(selection) > 0:
                        # assuming user meant to copy, not interrupt
                        # (IDLE seems to follow same logic)
                        return False
                except Exception:
                    # selection_get() gives error when calling without selection on Ubuntu
                    pass

        return self.is_running() or self.is_waiting_toplevel_command()

    def cmd_stop_restart(self):
        if get_workbench().in_simple_mode():
            get_workbench().hide_view("VariablesView")

        self.restart_backend(True)

    def disconnect(self):
        proxy = self.get_backend_proxy()
        assert hasattr(proxy, "disconnect")
        proxy.disconnect()

    def disconnect_enabled(self):
        return hasattr(self.get_backend_proxy(), "disconnect")

    def soft_reboot(self):
        proxy = self.get_backend_proxy()
        if hasattr(proxy, "_soft_reboot_and_run_main"):
            return proxy._soft_reboot_and_run_main()
        return None

    def soft_reboot_enabled(self):
        proxy = self.get_backend_proxy()
        return proxy and proxy.is_functional() and hasattr(proxy, "_soft_reboot_and_run_main")

    def _poll_vm_messages(self):
        """I chose polling instead of event_generate in listener thread,
        because event_generate across threads is not reliable
        http://www.thecodingforums.com/threads/more-on-tk-event_generate-and-threads.359615/
        """
        self._polling_after_id = None
        if self._pull_vm_messages() is False:
            return

        self._polling_after_id = GetApp().after(20, self._poll_vm_messages)

    def _pull_vm_messages(self):
        while self._proxy is not None:
            try:
                msg = self._proxy.fetch_next_message()
                if not msg:
                    break
                utils.get_logger().debug(
                    "RUNNER GOT: %s, %s in state: %s", msg.event_type, msg, self.get_state()
                )

            except BackendTerminatedError as exc:
                self._report_backend_crash(exc)
                self.destroy_backend()
                return False

            if msg.get("SystemExit", False):
                self.restart_backend(True)
                return False

            # change state
            if isinstance(msg, ToplevelResponse):
                self._set_state("waiting_toplevel_command")
            elif isinstance(msg, DebuggerResponse):
                self._set_state("waiting_debugger_command")
            else:
                "other messages don't affect the state"

            if "cwd" in msg:
                if not self.has_own_filesystem():
                    pass
                   # GetApp().set_local_cwd(msg["cwd"])

            # Publish the event
            # NB! This may cause another command to be sent before we get to postponed commands.
            try:
                self._publishing_events = True
                class_event_type = type(msg).__name__
                GetApp().event_generate(class_event_type, event=msg)  # more general event
                if msg.event_type != class_event_type:
                    # more specific event
                    GetApp().event_generate(msg.event_type, event=msg)
            finally:
                self._publishing_events = False

            # TODO: is it necessary???
            # https://stackoverflow.com/a/13520271/261181
            # get_workbench().update()

        self._send_postponed_commands()

    def _report_backend_crash(self, exc):
        returncode = getattr(exc, "returncode", "?")
        err = "Backend terminated or disconnected."

        try:
            faults_file = os.path.join(utils.get_app_path(), "backend_faults.log")
            if os.path.exists(faults_file):
                if utils.is_py3_plus():
                    with open(faults_file, encoding="ASCII") as fp:
                        err += fp.read()
                elif utils.is_py2():
                    with open(faults_file) as fp:
                        err += fp.read()
                        
        except Exception:
            utils.get_logger().exception("Failed retrieving backend faults")

        err = err.strip() + " Use 'Stop/Restart' to restart ...\n"

        if returncode != EXPECTED_TERMINATION_CODE:
            GetApp().event_generate("ProgramOutput", stream_name="stderr", data="\n" + err)

    #    get_workbench().become_active_window(False)
    
    def get_backend(self):
        return None

    def restart_backend(self, clean, first = False, wait = 0):
        """Recreate (or replace) backend proxy / backend process."""

        if not first:
            self.shell_view.restart()
            self.shell_view.update_idletasks()

        self.destroy_backend()
        backend_name = self.get_backend()
        if backend_name not in GetApp().get_backends():
            raise RuntimeError(
                "Can't find backend '{}'. Please select another backend from options".format(
                    backend_name
                )
            )

        backend_class = GetApp().get_backends()[backend_name].proxy_class
        self._set_state("running")
        self._proxy = None
        self._proxy = backend_class(clean)

        self._poll_vm_messages()

        if wait:
            start_time = time.time()
            while not self.is_waiting_toplevel_command() and time.time() - start_time <= wait:
                # self._pull_vm_messages()
                get_workbench().update()
                sleep(0.01)

        GetApp().event_generate("BackendRestart", full=True)

    def destroy_backend(self):
        if self._polling_after_id is not None:
            GetApp().after_cancel(self._polling_after_id)
            self._polling_after_id = None

        self._postponed_commands = []
        if self._proxy:
            self._proxy.destroy()
            self._proxy = None

        GetApp().event_generate("BackendTerminated")

    def get_local_executable(self):
        if self._proxy is None:
            return None
        else:
            return self._proxy.get_local_executable()

    def get_backend_proxy(self):
        return self._proxy

    def _check_alloc_console(self):
        if sys.executable.endswith("thonny.exe") or sys.executable.endswith("pythonw.exe"):
            # These don't have console allocated.
            # Console is required for sending interrupts.

            # AllocConsole would be easier but flashes console window

            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            exe = sys.executable.replace("thonny.exe", "python.exe").replace(
                "pythonw.exe", "python.exe"
            )

            cmd = [exe, "-c", "print('Hi!'); input()"]
            child = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
            )
            child.stdout.readline()
            result = kernel32.AttachConsole(child.pid)
            if not result:
                err = ctypes.get_last_error()
                utils.get_logger().info("Could not allocate console. Error code: " + str(err))
            child.stdin.write(b"\n")
            try:
                child.stdin.flush()
            except Exception:
                # May happen eg. when installation path has "&" in it
                # See https://bitbucket.org/plas/thonny/issues/508/cant-allocate-windows-console-when
                # Without flush the console window becomes visible, but Thonny can be still used
                utils.get_logger().exception("Problem with finalizing console allocation")

    def can_do_file_operations(self):
        return self._proxy and self._proxy.can_do_file_operations()

    def get_supported_features(self):
        if self._proxy is None:
            return set()
        else:
            return self._proxy.get_supported_features()

    def has_own_filesystem(self):
        if self._proxy is None:
            return False
        else:
            return self._proxy.has_own_filesystem()

    def get_node_label(self):
        if self._proxy is None:
            return "Back-end"
        else:
            return self._proxy.get_node_label()


class BackendProxy:
    """Communicates with backend process.
    
    All communication methods must be non-blocking, 
    ie. suitable for calling from GUI thread."""

    # backend_name will be overwritten on Workbench.add_backend
    # Subclasses don't need to worry about it.
    backend_name = None

    def __init__(self, clean):
        """Initializes (or starts the initialization of) the backend process.
        
        Backend is considered ready when the runner gets a ToplevelResponse
        with attribute "welcome_text" from fetch_next_message.
        """

    def send_command(self, cmd):
        """Send the command to backend. Return None, 'discard' or 'postpone'"""
        raise NotImplementedError()

    def send_program_input(self, data):
        """Send input data to backend"""
        raise NotImplementedError()

    def fetch_next_message(self):
        """Read next message from the queue or None if queue is empty"""
        raise NotImplementedError()

    def get_backend_name(self):
        return type(self).backend_name

    def interrupt(self):
        """Tries to interrupt current command without reseting the backend"""
        pass

    def destroy(self):
        """Called when Thonny no longer needs this instance 
        (Thonny gets closed or new backend gets selected)
        """
        pass

    def is_functional(self):
        """Used in MicroPython proxies"""
        return True

    def get_local_executable(self):
        """Return system command for invoking current interpreter"""
        return None

    def get_supported_features(self):
        return {"run"}

    def get_node_label(self):
        """Used as files caption if back-end has separate files"""
        return "Back-end"

    def has_own_filesystem(self):
        return False

    def uses_local_filesystem(self):
        return True

    def supports_directories(self):
        return True

    def can_do_file_operations(self):
        return False

    def get_cwd(self):
        return None
        
    def _get_initial_cwd(self):
        return None

class SubprocessProxy(BackendProxy):
    def __init__(self, clean, executable):
        BackendProxy.__init__(self,clean)

        self._executable = executable
        self._response_queue = None
        self._welcome_text = ""

        self._proc = None
        self._response_queue = None

        self._gui_update_loop_id = None
        self._cwd = self._get_initial_cwd()
        self._start_background_process()
        
    def _get_initial_cwd(self):
        return strutils.normpath_with_actual_case(os.path.expanduser("~"))
        
    def GetEnv(self):
        return None

    def _start_background_process(self):
        # deque, because in one occasion I need to put messages back
        self._response_queue = collections.deque()
        env = self.GetEnv()
        if not os.path.exists(self._executable):
            raise RuntimeError(
                "Interpreter (%s) not found. Please recheck corresponding option!"
                % self._executable
            )

        cmd_line = [
            self._executable,
            # (to avoid problems when using different Python versions without write permissions)
        ] + self._get_launcher_with_args()

        creationflags = 0
        startupinfo = None
        if utils.is_windows():
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        utils.get_logger().info("Starting the backend: %s %s", cmd_line, self._get_initial_cwd())
        self._proc = subprocess.Popen(
            cmd_line,
            # bufsize=0,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.get_cwd() if self.uses_local_filesystem() else None,
            env=env,
            universal_newlines=True,
            creationflags=creationflags,
            startupinfo = startupinfo
        )

        # setup asynchronous output listeners
        if utils.is_py2():
            t1 = Thread(target=self._listen_stdout, args=(self._proc.stdout,))
            t1.daemon=True
            t1.start()
            t2 = Thread(target=self._listen_stderr, args=(self._proc.stderr,))
            t2.daemon=True
            t2.start()
        elif utils.is_py3_plus():
            Thread(target=self._listen_stdout, args=(self._proc.stdout,), daemon=True).start()
            Thread(target=self._listen_stderr, args=(self._proc.stderr,), daemon=True).start()

    def _get_launcher_with_args(self):
        raise NotImplementedError()

    def send_command(self, cmd):
        """Send the command to backend. Return None, 'discard' or 'postpone'"""
        method_name = "_cmd_" + cmd.name
        if hasattr(self, method_name):
            return getattr(self, method_name)(cmd)

        if isinstance(cmd, ToplevelCommand) and cmd.name[0].isupper():
            self._clear_environment()

        self._send_msg(cmd)

    def _send_msg(self, msg):
        self._proc.stdin.write(serialize_message(msg) + "\n")
        self._proc.stdin.flush()

    def _clear_environment(self):
        pass

    def send_program_input(self, data):
        self._send_msg(InputSubmission(data))

    def _is_disconnected(self):
        return self._proc is None or self._proc.poll() is not None

    def interrupt(self):
        if self._proc is not None and self._proc.poll() is None:
            if running_on_windows():
                try:
                    os.kill(self._proc.pid, signal.CTRL_BREAK_EVENT)  # @UndefinedVariable
                except Exception:
                    utils.get_logger().exception("Could not interrupt backend process")
            else:
                self._proc.send_signal(signal.SIGINT)

    def destroy(self):
        self._close_backend()

    def _close_backend(self):
        if self._proc is not None and self._proc.poll() is None:
            self._proc.kill()

        self._proc = None
        self._response_queue = None

    def _listen_stdout(self, stdout):
        # debug("... started listening to stdout")
        # will be called from separate thread

        message_queue = self._response_queue

        def publish_as_msg(data):
            msg = parse_message(data)
            if "cwd" in msg:
                self.cwd = msg["cwd"]
            message_queue.append(msg)

            while len(message_queue) > 100:
                # Probably backend runs an infinite/long print loop.
                # Throttle message thougput in order to keep GUI thread responsive.
                sleep(0.1)

        while not self._is_disconnected():
            data = stdout.readline()
            # debug("... read some stdout data", repr(data))
            if data == "":
                break
            else:
                try:
                    publish_as_msg(data)
                except Exception:
                    traceback.print_exc()
                    # Can mean the line was from subprocess,
                    # which can't be captured by stream faking.
                    # NB! If subprocess printed it without linebreak,
                    # then the suffix can be thonny message

                    parts = data.rsplit(MESSAGE_MARKER, maxsplit=1)

                    # print first part as it is
                    message_queue.append(
                        BackendEvent("ProgramOutput", data=parts[0], stream_name="stdout")
                    )

                    if len(parts) == 2:
                        second_part = common.MESSAGE_MARKER + parts[1]
                        try:
                            publish_as_msg(second_part)
                        except Exception:
                            # just print ...
                            message_queue.append(
                                BackendEvent(
                                    "ProgramOutput", data=second_part, stream_name="stdout"
                                )
                            )

    def _listen_stderr(self, stderr):
        # stderr is used only for debugger debugging
        while not self._is_disconnected():
            data = stderr.readline()
            if data == "":
                break
            else:
                self._response_queue.append(
                    BackendEvent("ProgramOutput", stream_name="stderr", data=data)
                )

    def _store_state_info(self, msg):
        if "cwd" in msg:
            self._cwd = msg["cwd"]

        if "welcome_text" in msg:
            self._welcome_text = msg["welcome_text"]

        if "in_venv" in msg:
            self._in_venv = msg["in_venv"]

        if "path" in msg:
            self._sys_path = msg["path"]

        if "usersitepackages" in msg:
            self._usersitepackages = msg["usersitepackages"]

        if "prefix" in msg:
            self._sys_prefix = msg["prefix"]

        if "exe_dirs" in msg:
            self._exe_dirs = msg["exe_dirs"]

    def get_supported_features(self):
        return {"run"}

    def get_cwd(self):
        return self._cwd

    def get_exe_dirs(self):
        return self._exe_dirs

    def fetch_next_message(self):
        if not self._response_queue or len(self._response_queue) == 0:
            if self._is_disconnected():
                raise BackendTerminatedError(self._proc.returncode if self._proc else None)
            else:
                return None

        msg = self._response_queue.popleft()
        self._store_state_info(msg)

        if msg.event_type == "ProgramOutput":
            # combine available small output messages to one single message,
            # in order to put less pressure on UI code

            while True:
                if len(self._response_queue) == 0:
                    return msg
                else:
                    next_msg = self._response_queue.popleft()
                    if (
                        next_msg.event_type == "ProgramOutput"
                        and next_msg["stream_name"] == msg["stream_name"]
                        and len(msg["data"]) + len(next_msg["data"]) <= OUTPUT_MERGE_THRESHOLD
                        and ("\n" not in msg["data"] or not io_animation_required)
                    ):
                        msg["data"] += next_msg["data"]
                    else:
                        # not same type of message, put it back
                        self._response_queue.appendleft(next_msg)
                        return msg

        else:
            return msg
            
    def get_local_executable(self):
        return self._executable
        

def construct_cmd_line(parts, safe_tokens=[]):
    def quote(s):
        if s in safe_tokens:
            return s
        else:
            return shlex.quote(s)

    return " ".join(map(quote, parts))

def construct_cd_command(path):
    return construct_cmd_line(["%cd", strutils.normpath_with_actual_case(path)])
    

class BackendTerminatedError(Exception):
    def __init__(self, returncode=None):
        Exception.__init__(self)
        self.returncode = returncode

