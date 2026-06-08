project('xf86-input-svr4xqueue', 'c')

xorg_server = dependency('xorg-server')

shared_module('svr4xqueue_drv',
    'src/svr4xqueue.c',
    dependencies : xorg_server,
    name_prefix : '',
    install : true,
    install_dir : join_paths(get_option('libdir'), 'xorg/modules/input'))

install_data('conf/40-svr4xqueue.conf', install_dir : '/etc/X11/xorg.conf.d')
