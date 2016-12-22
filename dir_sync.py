"""Script to sync ncms intent directories.

"""

import os
import shutil

from google3.devtools.api.source.piper import piper_api_pb2
from google3.devtools.api.source.piper import pywrap_in_process
from google3.devtools.api.source.piper import source_file_pb2
from google3.devtools.piper.contrib.python.piper_api_wrapper import piper_api_wrapper
from google3.net.rpc.python import rpcutil
from google3.pyglib import app
from google3.pyglib import flags
from google3.pyglib import logging


FLAGS = flags.FLAGS
flags.DEFINE_string('folder', 'network_elements', 'directory folder to sync')
flags.DEFINE_string('workspace', 'net1', 'desired workspace name')

APP_TAG = 'ncms_cbf96'
USER = str(os.getlogin())
DEFAULT_WORKSPACE_NAME = 'net1'
ROOT_DIR = '/google/src/cloud/'+USER+'/'+DEFAULT_WORKSPACE_NAME+'/google3/'
ESPRESSO_CONFIG_DIR = 'configs/net/espresso/'
TARGET_DIR = 'experimental/ops/netops/lab/ncms/cbf96/'
IGNORE_FILES = ['METADATA', 'OWNERS', 'ncms_api_acl.gcl', 'BUILD']
IGNORE_PATTERNS = shutil.ignore_patterns(
    '*.dspec', 'testing', '*.acl', '*eacl', 'ncms_lock*')


class Error(Exception):
  """Generic exception class."""


class ServerResponseError(Error):
  """Raised when Piper API Server returns bad response."""


class PiperClient(object):
  """Client class for Piper wrapper.

  This class contains functions that execute tasks on Piper.
  """

  def __init__(self):

    self.piper_address = None
    self.stub = self._CreatePiperStub()
    self.piper_client = self._GetPiperClientFromWrapper()
    self.user = USER

  def _CreatePiperStub(self):
    """Creates a Piper API stub. See go/piper-api for more info.

    This module calls RunApiServer, which is an expensive operation.
    This script will use only one PiperClient() object at any given instance,
    hence this is added as part of initilization.

    Returns:
      Piper api stub object.
    """

    if not self.piper_address:
      self.piper_address = pywrap_in_process.RunApiServer()
    logging.info('Creating RPC channel')
    channel = rpcutil.GetNewChannel(self.piper_address)
    return piper_api_pb2.PiperApiService.NewRPC2Stub(channel=channel)

  def _GetPiperClientFromWrapper(self):
    """Creates a Piper client using piper_api_wrapper.

    Returns:
      Piper api client object used to perform piper tasks.
    """

    logging.info('Creating piper client from wrapper')
    return piper_api_wrapper.GetPiperApiWrapper(application_tag=APP_TAG,
                                                stub=self.stub)

  def CreateWorkspace(self, workspace_name):
    """Creates a Piper workspace.

    Args:
      workspace_name: Desired name for new workspace.

    Returns:
      Piper api client object used to perform piper tasks.

    Raises:
      ServerResponseError: Raised if piper server returned a NonZeroStaus.
    """
    try:
      for workspace in list(self.piper_client.ListWorkspaces(
          user_name=self.user)):
        if workspace.citc_alias == DEFAULT_WORKSPACE_NAME:
          self.piper_client.DeleteWorkspace(
              name=workspace.workspace_id.workspace_name, user_name=self.user,
              revert_pending_changes=True, remove_local_root=True)

          logging.info('Deleted stale workspace: "%s"', workspace.citc_alias)

      new_workspace = self.piper_client.CreateWorkspace(
          name=workspace_name, description='Workspace for-ncms sync script',
          multichange=False, user_name=self.user)
      logging.info('Created new workspace')
      return new_workspace
    except piper_api_wrapper.ServerReturnedNonZeroStatusError as e:
      raise ServerResponseError(e)

  def OverwriteFiles(self, src_dir, dest_dir):
    """Module to backup target directory files."""
    if os.path.exists(dest_dir):
      shutil.rmtree(dest_dir)
      logging.info('Deleted files in source directory')
    if os.path.exists(src_dir):
      shutil.copytree(src_dir, dest_dir)
      logging.info('Copied files to destination directory')

  def CreateNewCL(self, workspace):

    return self.piper_client.CreateChange(
        workspace_name=workspace, description='Change for testing ncms sync automation',
        user_name=self.user)

  def AddFilesToChange(self, change, workspace):
    self.piper_client.AddAllEditedFilesToChange(
        workspace_name=workspace, change_number=change, rpc_deadline=None)
    return self.piper_client.ComputeDiffStat(
        workspace_name=workspace, change_number=change,
        rpc_deadline=None, user_name=self.user)


def main(unused_argv):
  piper = PiperClient()
  workspace = piper.CreateWorkspace(DEFAULT_WORKSPACE_NAME)
  src_dir = ROOT_DIR+ESPRESSO_CONFIG_DIR+FLAGS.folder
  dest_dir = ROOT_DIR+TARGET_DIR+FLAGS.folder
  piper.OverwriteFiles(src_dir, dest_dir)
  cl = piper.CreateNewCL(workspace)
  deltaresponse = piper.AddFilesToChange(cl, workspace)

if __name__ == '__main__':
  app.run()
