###from __future__ import print_function
import sys
import os
import pickle
import config
import json
import types
import time
###from concurrent import futures
import functools
import multiprocessing
import fileparser
import utils

DATABASE_FILE = "version"

def generate_builtin_data(dest_path):
    def work_builtin_type(builtin_type,recursive=True):
        childs = []
        for name in dir(builtin_type):
            try:
                builtin_attr_intance = getattr(builtin_type,name)
            except:
                continue
            builtin_attr_type = type(builtin_attr_intance)
            if builtin_attr_type == types.TypeType:
                if not recursive:
                    continue
                builtin_attr_childs = work_builtin_type(builtin_attr_intance,False)
                node = dict(name = name,is_builtin=True,type = config.NODE_CLASSDEF_TYPE,childs=builtin_attr_childs)
                childs.append(node)
            elif builtin_attr_type == types.BuiltinFunctionType or builtin_attr_type == types.BuiltinMethodType \
                        or str(builtin_attr_type).find("method_descriptor") != -1:
                node = dict(name = name,is_builtin=True,type = config.NODE_FUNCDEF_TYPE)
                childs.append(node)
            else:
                node = dict(name = name,is_builtin=True,type = config.NODE_OBJECT_PROPERTY)
                childs.append(node)
        return childs
        
    dest_path = os.path.join(dest_path,"builtins")
    utils.MakeDirs(dest_path)
    for built_module in sys.builtin_module_names:
        module_instance = __import__(built_module)
        childs = work_builtin_type(module_instance)
        with open(dest_path + "/" + built_module + ".$memberlist", 'w') as f:
            for node in childs:
                f.write(node['name'])
                f.write('\n')
        module_dict = fileparser.make_module_dict(built_module,'',True,childs)
        with open(dest_path + "/" + built_module + ".$members", 'wb') as j:
            # Pickle dictionary using protocol 0.
            pickle.dump(module_dict, j)
            
def LoadDatabaseVersion(database_location):
    with open(os.path.join(database_location,DATABASE_FILE)) as f:
        return f.read()
        
def SaveDatabaseVersion(database_location,new_database_version):
    with open(os.path.join(database_location,DATABASE_FILE),"w") as f:
        f.write(new_database_version)
        
def NeedRenewDatabase(database_location,new_database_version):
    if not os.path.exists(os.path.join(database_location,DATABASE_FILE)):
        return True
    old_database_version = LoadDatabaseVersion(database_location)
    if 0 == utils.CompareDatabaseVersion(new_database_version,old_database_version):
        return False
    return True
           
def generate_intelligent_data(root_path,new_database_version):
    if isinstance(sys.version_info,tuple):
        version = str(sys.version_info[0]) + "." +  str(sys.version_info[1]) 
        if sys.version_info[2] > 0:
            version += "."
            version += str(sys.version_info[2])
    else:
        version = str(sys.version_info.major) + "." +  str(sys.version_info.minor) + "."  + str(sys.version_info.micro)
    dest_path = os.path.join(root_path,version)
    utils.MakeDirs(dest_path)
    need_renew_database = NeedRenewDatabase(dest_path,new_database_version)
    sys_path_list = sys.path
    for i,path in enumerate(sys_path_list):
        sys_path_list[i] = os.path.abspath(path)
    for path in sys_path_list:
        print ('start parse path data',path)
        scan_sys_path(path,dest_path,need_renew_database)
    if need_renew_database:
        SaveDatabaseVersion(dest_path,new_database_version)

def quick_generate_intelligent_data(root_path):
    version = str(sys.version_info.major) + "." +  str(sys.version_info.minor) + "."  + str(sys.version_info.micro)
    dest_path = os.path.join(root_path,version)
    utils.MakeDirs(dest_path)
    sys_path_list = sys.path
    for i,path in enumerate(sys_path_list):
        sys_path_list[i] = os.path.abspath(path)
    with futures.ThreadPoolExecutor(max_workers=len(sys_path_list)) as controller:
        future_list = []
        for path in sys_path_list:
            print ('start parse path data',path)
            scan_path_handler = functools.partial(scan_sys_path,path,dest_path)
            scan_path_future = controller.submit(scan_path_handler)
            future_list.append(scan_path_future)
  #      results = futures.wait(future_list,return_when=futures.FIRST_EXCEPTION)
   #     finished, unfinished = results
    #    for future in finished:
     #       future.result()
     
def generate_intelligent_data_by_pool(root_path,new_database_version):
    if isinstance(sys.version_info,tuple):
        version = str(sys.version_info[0]) + "." +  str(sys.version_info[1]) 
        if sys.version_info[2] > 0:
            version += "."
            version += str(sys.version_info[2])
    else:
        version = str(sys.version_info.major) + "." +  str(sys.version_info.minor) + "."  + str(sys.version_info.micro)
    dest_path = os.path.join(root_path,version)
    utils.MakeDirs(dest_path)
    need_renew_database = NeedRenewDatabase(dest_path,new_database_version)
    sys_path_list = sys.path
    max_pool_count = 5
    for i,path in enumerate(sys_path_list):
        sys_path_list[i] = os.path.abspath(path)
    pool = multiprocessing.Pool(processes=min(max_pool_count,len(sys_path_list)))
    future_list = []
    for path in sys_path_list:
        print ('start parse path data',path)
        pool.apply_async(scan_sys_path,(path,dest_path,need_renew_database))
    pool.close()
    pool.join()
    if need_renew_database:
        SaveDatabaseVersion(dest_path,new_database_version)
     
def scan_sys_path(src_path,dest_path,need_renew_database):

    def is_path_ignored(path):
        for ignore_path in ignore_path_list:
            if path.startswith(ignore_path):
                return True
        return False
    ignore_path_list = []
    for root,path,files in os.walk(src_path):
        if is_path_ignored(root):
            continue
        if root != src_path and is_test_dir(root):
            ignore_path_list.append(root)
          ##  print ('path',root,'is a test dir')
            continue
        elif root != src_path and not fileparser.is_package_dir(root):
            ignore_path_list.append(root)
           ### print ('path',root,'is not a package dir')
            continue
        for afile in files:
            fullpath = os.path.join(root,afile)
            ext = os.path.splitext(fullpath)[1]
            if not ext in ['.py','.pyw']:
                continue
            top_module_name,is_package = utils.get_top_modulename(fullpath)
            if top_module_name == "":
                continue
            module_members_file = os.path.join(dest_path,top_module_name+ ".$members")
            if os.path.exists(module_members_file) and not need_renew_database:
             ###   print fullpath,'has been already analyzed'
                continue
            #print get_data_name(fullpath)
           # with open("filelist.txt","a") as f:
            #    print (fullpath,file=f)
            fileparser.dump(fullpath,top_module_name,dest_path,is_package)
           
def is_test_dir(dir_path):
    dir_name = os.path.basename(dir_path)
    if dir_name.lower() == "test" or dir_name.lower() == "tests":
        return True
    else:
        return False
    
if __name__ == "__main__":
    start_time = time.time()
    root_path = sys.argv[1]
    new_database_version = sys.argv[2]
  ###  generate_builtin_data('./')
    ##generate_intelligent_data(root_path,new_database_version)
    ###quick_generate_intelligent_data("interlicense")
    generate_intelligent_data_by_pool(root_path,new_database_version)
    end_time = time.time()
    elapse = end_time - start_time
    print ('elapse time:',elapse,'s')
    print ('end............')