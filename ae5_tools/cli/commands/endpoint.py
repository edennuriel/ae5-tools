import click

from ..login import login_options, cluster_call
from ..format import print_output, format_options


@click.group(short_help='info, list',
             epilog='Type "ae5 endpoint <command> --help" for help on a specific command.')
@format_options()
@login_options()
def endpoint():
    pass


@endpoint.command()
@format_options()
@login_options()
def list():
    '''List the static endpoints on this cluster.
    '''
    result = cluster_call('endpoint_list', format='dataframe')
    print_output(result)


@endpoint.command()
@click.argument('endpoint')
@format_options()
@login_options()
def info(endpoint):
    '''Retrieve the record of a single endpoint.

       The ENDPOINT identifier need not be fully specified, and may even include
       wildcards. But it must match exactly one endpoint name or ID.
    '''
    result = cluster_call('endpoint_info', endpoint, format='dataframe')
    print_output(result)
