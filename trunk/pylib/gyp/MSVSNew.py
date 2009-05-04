#!/usr/bin/python2.4

"""New implementation of Visual Studio project generation for SCons."""

import common
import os
import random

# hashlib is supplied as of Python 2.5 as the replacement interface for md5
# and other secure hashes.  In 2.6, md5 is deprecated.  Import hashlib if
# available, avoiding a deprecation warning under 2.6.  Import md5 otherwise,
# preserving 2.4 compatibility.
try:
  import hashlib
  _new_md5 = hashlib.md5
except ImportError:
  import md5
  _new_md5 = md5.new


# Initialize random number generator
random.seed()

# GUIDs for project types
ENTRY_TYPE_GUIDS = {
    'project': '{8BC9CEB8-8B4A-11D0-8D11-00A0C91BC942}',
    'folder': '{2150E333-8FDC-42A3-9474-1A3956D46DE8}',
}

#------------------------------------------------------------------------------
# Helper functions


def MakeGuid(name, seed='msvs_new'):
  """Returns a GUID for the specified target name.

  Args:
    name: Target name.
    seed: Seed for MD5 hash.
  Returns:
    A GUID-line string calculated from the name and seed.

  This generates something which looks like a GUID, but depends only on the
  name and seed.  This means the same name/seed will always generate the same
  GUID, so that projects and solutions which refer to each other can explicitly
  determine the GUID to refer to explicitly.  It also means that the GUID will
  not change when the project for a target is rebuilt.
  """
  # Calculate a MD5 signature for the seed and name.
  d = _new_md5(str(seed) + str(name)).hexdigest().upper()
  # Convert most of the signature to GUID form (discard the rest)
  guid = ('{' + d[:8] + '-' + d[8:12] + '-' + d[12:16] + '-' + d[16:20]
          + '-' + d[20:32] + '}')
  return guid

#------------------------------------------------------------------------------


class MSVSFolder:
  """Folder in a Visual Studio project or solution."""

  def __init__(self, name, entries = None, guid = None, items = None):
    """Initializes the folder.

    Args:
      name: Name of folder.
      entries: List of folder entries to nest inside this folder.  May contain
          Folder or Project objects.  May be None, if the folder is empty.
      guid: GUID to use for folder, if not None.
      items: List of solution items to include in the folder project.  May be
          None, if the folder does not directly contain items.
    """
    self.name = name

    # For folder entries, the path is the same as the name
    self.path = name

    self.guid = guid

    # Copy passed lists (or set to empty lists)
    self.entries = list(entries or [])
    self.items = list(items or [])

    self.entry_type_guid = ENTRY_TYPE_GUIDS['folder']

  def get_guid(self):
    if self.guid is None:
      # Use consistent guids for folders (so things don't regenerate).
      self.guid = MakeGuid(self.path, seed='msvs_folder')
    return self.guid


#------------------------------------------------------------------------------


class MSVSProject:
  """Visual Studio project."""

  def __init__(self, path, name = None, dependencies = None, guid = None):
    """Initializes the project.

    Args:
      path: Relative path to project file.
      name: Name of project.  If None, the name will be the same as the base
          name of the project file.
      dependencies: List of other Project objects this project is dependent
          upon, if not None.
      guid: GUID to use for project, if not None.
    """
    self.path = path
    self.guid = guid

    if name:
      self.name = name
    else:
      # Use project filename
      self.name = os.path.splitext(os.path.basename(path))[0]

    # Copy passed lists (or set to empty lists)
    self.dependencies = list(dependencies or [])

    self.entry_type_guid = ENTRY_TYPE_GUIDS['project']

  def get_guid(self):
    if self.guid is None:
      # Set GUID from path
      # TODO(rspangler): This is fragile.
      # 1. We can't just use the project filename sans path, since there could
      #    be multiple projects with the same base name (for example,
      #    foo/unittest.vcproj and bar/unittest.vcproj).
      # 2. The path needs to be relative to $SOURCE_ROOT, so that the project
      #    GUID is the same whether it's included from base/base.sln or
      #    foo/bar/baz/baz.sln.
      # 3. The GUID needs to be the same each time this builder is invoked, so
      #    that we don't need to rebuild the solution when the project changes.
      # 4. We should be able to handle pre-built project files by reading the
      #    GUID from the files.
      self.guid = MakeGuid(self.name)
    return self.guid

#------------------------------------------------------------------------------


class MSVSSolution:
  """Visual Studio solution."""

  def __init__(self, path, entries = None, variants = None, websiteProperties = True):
    """Initializes the solution.

    Args:
      path: Path to solution file.
      entries: List of entries in solution.  May contain Folder or Project
          objects.  May be None, if the folder is empty.
      variants: List of build variant strings.  If none, a default list will
          be used.
    """
    self.path = path
    self.websiteProperties = websiteProperties

    # Copy passed lists (or set to empty lists)
    self.entries = list(entries or [])

    if variants:
      # Copy passed list
      self.variants = variants[:]
    else:
      # Use default
      self.variants = ['Debug|Win32', 'Release|Win32']
    # TODO(rspangler): Need to be able to handle a mapping of solution config
    # to project config.  Should we be able to handle variants being a dict,
    # or add a separate variant_map variable?  If it's a dict, we can't
    # guarantee the order of variants since dict keys aren't ordered.


    # TODO(rspangler): Automatically write to disk for now; should delay until
    # node-evaluation time.
    self.Write()


  def Write(self, writer = common.WriteOnDiff):
    """Writes the solution file to disk.

    Raises:
      IndexError: An entry appears multiple times.
    """
    # Walk the entry tree and collect all the folders and projects.
    all_entries = []
    entries_to_check = self.entries[:]
    while entries_to_check:
      # Pop from the beginning of the list to preserve the user's order.
      e = entries_to_check.pop(0)

      # A project or folder can only appear once in the solution's folder tree.
      # This also protects from cycles.
      if e in all_entries:
        #raise IndexError('Entry "%s" appears more than once in solution' %
        #                 e.name)
        continue

      all_entries.append(e)

      # If this is a folder, check its entries too.
      if isinstance(e, MSVSFolder):
        entries_to_check += e.entries

    # Open file and print header
    f = writer(self.path)
    f.write('Microsoft Visual Studio Solution File, Format Version 9.00\r\n')
    f.write('# Visual Studio 2005\r\n')

    # Project entries
    for e in all_entries:
      f.write('Project("%s") = "%s", "%s", "%s"\r\n' % (
          e.entry_type_guid,          # Entry type GUID
          e.name,                     # Folder name
          e.path.replace('/', '\\'),  # Folder name (again)
          e.get_guid(),               # Entry GUID
      ))

      # TODO(rspangler): Need a way to configure this stuff
      if self.websiteProperties:
        f.write('\tProjectSection(WebsiteProperties) = preProject\r\n'
                '\t\tDebug.AspNetCompiler.Debug = "True"\r\n'
                '\t\tRelease.AspNetCompiler.Debug = "False"\r\n'
                '\tEndProjectSection\r\n')

      if isinstance(e, MSVSFolder):
        if e.items:
          f.write('\tProjectSection(SolutionItems) = preProject\r\n')
          for i in e.items:
            f.write('\t\t%s = %s\r\n' % (i, i))
          f.write('\tEndProjectSection\r\n')

      if isinstance(e, MSVSProject):
        if e.dependencies:
          f.write('\tProjectSection(ProjectDependencies) = postProject\r\n')
          for d in e.dependencies:
            f.write('\t\t%s = %s\r\n' % (d.get_guid(), d.get_guid()))
          f.write('\tEndProjectSection\r\n')

      f.write('EndProject\r\n')

    # Global section
    f.write('Global\r\n')

    # Configurations (variants)
    f.write('\tGlobalSection(SolutionConfigurationPlatforms) = preSolution\r\n')
    for v in self.variants:
      f.write('\t\t%s = %s\r\n' % (v, v))
    f.write('\tEndGlobalSection\r\n')

    # Sort config guids for easier diffing of solution changes.
    config_guids = []
    for e in all_entries:
      if isinstance(e, MSVSProject):
        config_guids.append(e.get_guid())
    config_guids.sort()

    f.write('\tGlobalSection(ProjectConfigurationPlatforms) = postSolution\r\n')
    for g in config_guids:
      for v in self.variants:
        f.write('\t\t%s.%s.ActiveCfg = %s\r\n' % (
            g,              # Project GUID
            v,              # Solution build configuration
            v,              # Project build config for that solution config
        ))

        # Enable project in this solution configuratation
        f.write('\t\t%s.%s.Build.0 = %s\r\n' % (
            g,              # Project GUID
            v,              # Solution build configuration
            v,              # Project build config for that solution config
        ))
    f.write('\tEndGlobalSection\r\n')

    # TODO(rspangler): Should be able to configure this stuff too (though I've
    # never seen this be any different)
    f.write('\tGlobalSection(SolutionProperties) = preSolution\r\n')
    f.write('\t\tHideSolutionNode = FALSE\r\n')
    f.write('\tEndGlobalSection\r\n')

    # Folder mappings
    # TODO(rspangler): Should omit this section if there are no folders
    f.write('\tGlobalSection(NestedProjects) = preSolution\r\n')
    for e in all_entries:
      if not isinstance(e, MSVSFolder):
        continue        # Does not apply to projects, only folders
      for subentry in e.entries:
        f.write('\t\t%s = %s\r\n' % (subentry.get_guid(), e.get_guid()))
    f.write('\tEndGlobalSection\r\n')

    f.write('EndGlobal\r\n')

    f.close()
