import click
import webbrowser
import re

from ..login import cluster_call, login_options
from ..utils import add_param, ident_filter, get_options
from ..format import print_output, format_options
from ...identifier import Identifier
from .deployment_collaborator import collaborator


@click.group(short_help='collaborator, info, list, open, patch, restart, start, stop',
             epilog='Type "ae5 deployment <command> --help" for help on a specific command.')
@format_options()
@login_options()
def deployment():
    '''Commands related to project deployments.'''
    pass


deployment.add_command(collaborator)


@deployment.command()
@ident_filter('deployment')
@click.option('--collaborators', is_flag=True, help='Include collaborators. Since this requires an API call for each project, it can be slow if there are large numbers of projects.')
@format_options()
@login_options()
def list(collaborators):
    '''List available deployments.

       By default, lists all deployments visible to the authenticated user.
       Simple filters on owner, project name, or id can be performed by
       supplying an optional DEPLOYMENT argument. Filters on other fields may
       be applied using the --filter option.
    '''
    cluster_call('deployment_list', collaborators=collaborators, cli=True)


@deployment.command()
@click.argument('deployment')
@format_options()
@login_options()
def info(deployment):
    '''Retrieve information about a single deployment.

       The DEPLOYMENT identifier need not be fully specified, and may even include
       wildcards. But it must match exactly one project.
    '''
    cluster_call('deployment_info', deployment, cli=True)


@deployment.command()
@click.argument('deployment')
@click.option('--public', is_flag=True, help='Make the deployment public.')
@click.option('--private', is_flag=True, help='Make the deployment private.')
@format_options()
@login_options()
def patch(deployment, public, private):
    '''Change a deployment's public/private status.

       The DEPLOYMENT identifier need not be fully specified, and may even include
       wildcards. But it must match exactly one deployment.
    '''
    if public and private:
        raise click.ClickException('Cannot specify both --public and --private')
    if not public and not private:
        public = None
    cluster_call('deployment_patch', deployment, public=public, cli=True)


def _open(record, frame):
    scheme, _, hostname, _ = record['project_url'].split('/', 3)
    if frame:
        url = f'{scheme}//{hostname}/deployments/detail/{record["id"]}/view'
    else:
        url = record['url']
    webbrowser.open(url, 1, True)


@deployment.command(short_help='Start a deployment for a project.')
@click.argument('project')
@click.option('--name', type=str, required=False, help="Deployment name. If not supplied, it is autogenerated from the project name.")
@click.option('--endpoint', type=str, required=False, help='Endpoint name. If not supplied, a generated subdomain will be used.')
@click.option('--command', help='The command to use for this deployment.')
@click.option('--resource-profile', help='The resource profile to use for this deployment.')
@click.option('--public', is_flag=True, help='Make the deployment public.')
@click.option('--private', is_flag=True, help='Make the deployment private (the default).')
@click.option('--wait', is_flag=True, help='Wait for the deployment to complete initialization before exiting.')
@click.option('--open', is_flag=True, help='Open a browser upon initialization. Implies --wait.')
@click.option('--frame', is_flag=True, help='Include the AE banner when opening.')
@format_options()
@login_options()
@click.pass_context
def start(ctx, project, name, endpoint, command, resource_profile, public, private, wait, open, frame):
    '''Start a deployment for a project.

       The PROJECT identifier need not be fully specified, and may even include
       wildcards. But it must match exactly one project.

       If the static endpoint is supplied, it must be of the form r'[A-Za-z0-9-]+',
       and it will be converted to lowercase. It must not match any endpoint with
       an active deployment, nor can it match any endpoint claimed by another project,
       even if that project has no active deployments. If the endpoint is not supplied,
       it will be autogenerated from the project name.

       By default, this command will wait for the completion of the deployment
       creation before returning. To return more quickly, use the --no-wait option.
    '''
    if public and private:
        raise click.ClickException('Cannot specify both --public and --private')
    if endpoint:
        endpoints = cluster_call('endpoint_list', format='json')
        if not re.match(r'[A-Za-z0-9-]+', endpoint):
            click.ClickException(f'Invalid endpoint: {endpoint}')
        prec = cluster_call('project_info', project, collaborators=False, format='json')
        for e in endpoints:
            if e['id'] != endpoint:
                continue
            elif e['deployment_id']:
                raise click.ClickException(f'Endpoint {endpoint} is already active')
            elif e['owner'] and e['owner'] != prec['owner']:
                raise click.ClickException(f'Endpoint {endpoint} is claimed by user {e["owner"]}')
            elif e['project_id'] and e['project_id'] != prec['id']:
                raise click.ClickException(f'Endpoint {endpoint} is claimed by project {e["project_name"]}')
    name_s = f' {name}' if name else ''
    endpoint_s = f' at endpoint {endpoint}' if endpoint else ''
    response = cluster_call('deployment_start', ident=project, id_class='project',
                            name=name if name else None,
                            endpoint=endpoint, command=command,
                            resource_profile=resource_profile, public=public,
                            wait=wait or open,
                            prefix=f'Starting deployment{name_s}{endpoint_s} for {{ident}}...',
                            postfix='started.')
    if open:
        _open(response, frame)
    print_output(response)


@deployment.command(short_help='Restart a deployment for a project.')
@click.argument('deployment')
@click.option('--wait', is_flag=True, help='Wait for the deployment to complete initialization before exiting.')
@click.option('--open', is_flag=True, help='Open a browser upon initialization. Implies --wait.')
@click.option('--frame', is_flag=True, help='Include the AE banner when opening.')
@format_options()
@login_options()
@click.pass_context
def restart(ctx, deployment, wait, open, frame):
    '''Restart a deployment for a project.

       The DEPLOYMENT identifier need not be fully specified, and may even include
       wildcards. But it must match exactly one project.
    '''
    cluster_call('deployment_restart', ident=deployment,
                 wait=wait or open,
                 prefix='Restarting deployment {ident}...', 
                 postfix='restarted.')
    if open:
        _open(response, frame)


@deployment.command(short_help='Stop a deployment.')
@click.argument('deployment')
@click.option('--yes', is_flag=True, help='Do not ask for confirmation.')
@format_options()
@login_options()
def stop(deployment, yes):
    '''Stop a deployment.

       The DEPLOYMENT identifier need not be fully specified, and may even include
       wildcards. But it must match exactly one project.
    '''
    cluster_call('deployment_stop', ident=deployment,
                 confirm=None if yes else 'Stop deployment {ident}',
                 prefix='Stopping {ident}...',
                 postfix='stopped.')


@deployment.command(short_help='Open a deployment in a browser.')
@click.argument('deployment')
@click.option('--frame/--no-frame', default=False, help='Include the AE banner.')
@format_options()
@login_options()
def open(deployment, frame):
    '''Opens a deployment in the default browser.

       The DEPLOYMENT identifier need not be fully specified, and may even include
       wildcards. But it must match exactly one session.

       For deployments, the frameless version of the deployment will be opened by
       default. If you wish to the Anaconda Enterprise banner at the top
       of the window, use the --frame option.
    '''
    result = cluster_call('deployment_info', deployment, format='json')
    _open(result, frame)
