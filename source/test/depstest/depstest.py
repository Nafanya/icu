#! /usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2011, International Business Machines
# Corporation and others. All Rights Reserved.
#
# file name: depstest.py
#
# created on: 2011may24

"""ICU dependency tester.

This probably works only on Linux.

The exit code is 0 if everything is fine, 1 for errors, 2 for only warnings.

Sample invocation:
  ~/svn.icu/trunk/src/source/test/depstest$ ./depstest.py ~/svn.icu/trunk/dbg
"""

__author__ = "Markus W. Scherer"

import glob
import os.path
import subprocess
import sys

import dependencies

_ignored_symbols = set()
_obj_files = {}
_symbols_to_files = {}
_return_value = 0

def _ReadObjFile(root_path, library_name, obj_name):
  global _ignored_symbols, _obj_files, _symbols_to_files
  lib_obj_name = library_name + "/" + obj_name
  if lib_obj_name in _obj_files:
    print "duplicate " + lib_obj_name
    return

  path = os.path.join(root_path, library_name, obj_name)
  nm_result = subprocess.Popen(["nm", "--demangle", "--format=sysv",
                                "--extern-only", "--no-sort", path],
                               stdout=subprocess.PIPE).communicate()[0]
  obj_imports = set()
  obj_exports = set()
  for line in nm_result.splitlines():
    fields = line.split("|")
    if len(fields) == 1: continue
    name = fields[0].strip()
    # Ignore symbols like '__cxa_pure_virtual',
    # 'vtable for __cxxabiv1::__si_class_type_info' or
    # 'DW.ref.__gxx_personality_v0'.
    if name.startswith("__cxa") or "__cxxabi" in name or "__gxx" in name:
      _ignored_symbols.add(name)
      continue
    type = fields[2].strip()
    if type == "U":
      obj_imports.add(name)
    else:
      # TODO: Investigate weak symbols (V, W) with or without values.
      obj_exports.add(name)
      _symbols_to_files[name] = lib_obj_name
  _obj_files[lib_obj_name] = {"imports": obj_imports, "exports": obj_exports}

def _ReadLibrary(root_path, library_name):
  obj_paths = glob.glob(os.path.join(root_path, library_name, "*.o"))
  for path in obj_paths:
    _ReadObjFile(root_path, library_name, os.path.basename(path))

def _GetExports(name, parents):
  global _ignored_symbols, _obj_files, _symbols_to_files, _return_value
  item = dependencies.items[name]
  item_type = item["type"]
  if name in parents:
    sys.exit("Error: %s %s has a circular dependency on itself: %s" %
             (item_type, name, parents))
  # TODO: print "** %s %s" % (parents, name)
  # Check if already cached.
  exports = item.get("exports")
  if exports != None: return exports
  # Calculcate recursively.
  parents.append(name)
  imports = set()
  exports = set()
  files = item.get("files")
  if files:
    for file_name in files:
      obj_file = _obj_files[file_name]
      imports |= obj_file["imports"]
      exports |= obj_file["exports"]
  imports -= exports | _ignored_symbols
  deps = item.get("deps")
  if deps:
    for dep in deps:
      dep_exports = _GetExports(dep, parents)
      # Detect whether this item needs to depend on dep,
      # except when this item has no files, that is, when it is just
      # a deliberate umbrella group or library.
      if files and imports.isdisjoint(dep_exports):
        print "Info:  %s %s  does not need to depend on  %s\n" % (item_type, name, dep)
      # We always include the dependency's exports, even if we do not need them
      # to satisfy local imports.
      exports |= dep_exports
  item["exports"] = exports
  imports -= exports
  for symbol in imports:
    for file_name in files:
      if symbol in _obj_files[file_name]["imports"]:
        sys.stderr.write("Error:  %s %s  file  %s  imports  %s  but  %s  does not depend on  %s\n" %
                         (item_type, name, file_name, symbol, name, _symbols_to_files.get(symbol)))
    _return_value = 1
  del parents[-1]
  return exports

def main():
  global _ignored_symbols, _obj_files, _return_value
  if len(sys.argv) <= 1:
    sys.exit(("Command line error: " +
             "need one argument with the root path to the built ICU libraries/*.o files."))
  dependencies.Load()
  system_symbols = dependencies.items.get("system_symbols")
  if system_symbols:
    for symbol in system_symbols["exports"]:
      _symbols_to_files[symbol] = "system_symbols"
  for library_name in dependencies.libraries:
    _ReadLibrary(sys.argv[1], library_name)
  o_files_set = set(_obj_files.keys())
  files_missing_from_deps = o_files_set - dependencies.files
  files_missing_from_build = dependencies.files - o_files_set
  if files_missing_from_deps:
    sys.stderr.write("Error: files missing from dependencies.txt:\n%s\n" %
                     sorted(files_missing_from_deps))
    _return_value = 1
  if files_missing_from_build:
    sys.stderr.write("Error: files in dependencies.txt but not built:\n%s\n" %
                     sorted(files_missing_from_build))
    _return_value = 1
  if _ignored_symbols:
    print "Info: ignored symbols:\n%s" % sorted(_ignored_symbols)
  if not _return_value:
    for library_name in dependencies.libraries:
      _GetExports(library_name, [])
  # TODO: print ".o files:\n%s" % _obj_files
  # TODO: print "items:\n%s" % dependencies.items
  if not _return_value:
    print "OK: Specified and actual dependencies match."
  return _return_value

if __name__ == "__main__":
  sys.exit(main())
