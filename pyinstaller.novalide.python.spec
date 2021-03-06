# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

#注意运行C:\Users\Administrator\AppData\Local\Programs\Python\Python36-32\Scripts\pyinstaller.exe pyinstaller.novalide.python.spec的时候不能在编辑器里面打开的终端中操作
#必须在操作文件系统里面打开终端

#程序数据文件列表,第一列表示源文件路径,第二列表示目的相对路径
datas = [
    ("noval/syntax/lexer/*.py","noval/syntax/lexer"),
    ("noval/python/syntax/lexer/*.py","noval/python/syntax/lexer"),
        #这里必须用*.*通配符否则会把所有子目录的图片都放在根目录下,*表示所有子文件以及目录
    ("noval/bmp_source/*.*","noval/bmp_source"),
    ("noval/bmp_source/checkbox/*","noval/bmp_source/checkbox"),
    ("noval/bmp_source/project/*","noval/bmp_source/project"),
    ("noval/bmp_source/file/*","noval/bmp_source/file"),
    ("noval/bmp_source/files/*","noval/bmp_source/files"),
    ("noval/bmp_source/toolbar/*","noval/bmp_source/toolbar"),
    ("noval/bmp_source/python/outline/*","noval/bmp_source/python/outline"),
    ("noval/bmp_source/project/python/*.*","noval/bmp_source/project/python"),
    ("noval/bmp_source/python/*.*","noval/bmp_source/python"),
    ("noval/bmp_source/python/debugger/*","noval/bmp_source/python/debugger"),
    ("noval/data/template/*.tar.bz2","noval/data/template"),
    ("noval/data/sample/*.sample","noval/data/sample"),
    ('locale/en_US/LC_MESSAGES/*.mo',"locale/en_US/LC_MESSAGES"),
    ('locale/zh_CN/LC_MESSAGES/*.mo',"locale/zh_CN/LC_MESSAGES"),
    ("noval/python/explain_environment.py","noval/python"),
    ("noval/python/parser/*.py","noval/python/parser"),
    ("noval/plugins/*.py","noval/plugins"),
    ("noval/python/plugins/*.py","noval/python/plugins"),
    ("noval/python/plugins/pyshell/*.py","noval/python/plugins/pyshell"),
    ("noval/util/command.py","noval/util"),
    ("noval/plugins/printer/*.*","noval/plugins/printer"),
    ('noval/python/project/browser.py','noval/python/project'),
    ('noval/python/project/pages/*.py','noval/python/project/pages'),
    ("noval/find/findresult.py","noval/find"),
    ('noval/python/debugger/debuggerharness.py','noval/python/debugger'),
    ('noval/python/debugger/debuggerharness3.py','noval/python/debugger'),
    ('noval/python/debugger/inspectconsole.py','noval/python/debugger'),
    ('noval/python/debugger/breakpoints.py','noval/python/debugger'),
    ('noval/python/debugger/watchs.py','noval/python/debugger'),
    ('noval/python/debugger/stacksframe.py','noval/python/debugger'),
    ("./tkdnd/*.*","./tkdnd"),
    ("noval.ico","./"),
    ("version.txt","./"),
    ("template.xml","./"),
]
a = Analysis(['NovalIDE.py'],
             pathex=['./'],
             binaries=[],
             datas=datas,
             hiddenimports=['noval.util.downutils','noval.python.pyeditor','noval.syntax.pat','site','noval.running','noval.shell','noval.roughparse'],
             hookspath=[],
             runtime_hooks=[],
             excludes=['noval.util.command'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
#console为False表示非控制台界面
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='NovalIDE',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False , icon='./noval.ico')
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='NovalIDE')
