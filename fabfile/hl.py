#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2016
#    Copyright by UWA (in the framework of the ICRAR)
#    All rights reserved
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston,
#    MA 02111-1307  USA
#
"""
Module with a few high-level fabric tasks users are likely to use
"""

import os

from fabric.decorators import task, parallel
from fabric.operations import local
from fabric.state import env
from fabric.tasks import execute

from aws import create_aws_instances
from dockerContainer import create_stage1_docker_container, create_stage2_docker_image, create_final_docker_image
from ngas import install_and_check, prepare_install_and_check, create_sources_tarball, upload_to
from utils import repo_root, check_ssh, append_desc
from system import check_sudo


# Don't re-export the tasks imported from other modules, only ours
__all__ = ['user_deploy', 'operations_deploy', 'aws_deploy', 'docker_image',
           'prepare_release']

@task
@parallel
@append_desc
def user_deploy():
    """Compiles and installs NGAS in a user-owned directory."""
    check_ssh()
    install_and_check()

@task
@parallel
@append_desc
def operations_deploy():
    """Performs a system-level setup on a host and installs NGAS on it"""
    check_ssh()
    check_sudo()
    prepare_install_and_check()

@task
@append_desc
def aws_deploy():
    """Deploy NGAS on fresh AWS EC2 instances."""
    # This task doesn't have @parallel because its initial work
    # (actually *creating* the target host(s)) is serial.
    # After that it modifies the env.hosts to point to the target hosts
    # and then calls execute(prepare_install_and_check) which will be parallel
    create_aws_instances()
    execute(prepare_install_and_check)

@task
def docker_image():
    """
    Create a Docker image running NGAS.
    """
    # Build and start the stage1 container holding onto the container info to use later.
    dockerState = create_stage1_docker_container()
    if not dockerState:
        return

    # Now install into the docker container.
    # We assume above has set the environment host IP address to install into
    execute(prepare_install_and_check)

    # Now that NGAS is istalled in container do cleanup on it and build final image.
    if not create_stage2_docker_image(dockerState):
        return

    # Now build the final NGAS docker image
    if not create_final_docker_image(dockerState):
        # This is not really needed by included in case code is added below this point
        return

@task
def prepare_release():
    """
    Prepares an NGAS release (deploys NGAS into AWS serving its own source/doc)
    """

    # Create the AWS instance
    aws_deploy()

    # Create and upload the sources
    sources = "ngas_src.tar.gz"
    if os.path.exists(sources):
        os.unlink(sources)
    create_sources_tarball(sources)
    try:
        upload_to(env.hosts[0], sources)
    finally:
        os.unlink(sources)

    # Generate a PDF documentation and upload it too
    local("make -C %s/doc latexpdf" % (repo_root()))
    upload_to(env.hosts[0], '%s/doc/_build/latex/ngas.pdf' % (repo_root()))