project('xf86-video-svr4ws', 'c')

xorg_server = dependency('xorg-server')

shared_module('svr4ws_drv',
    'src/svr4ws_driver.c',
    dependencies : xorg_server,
    name_prefix : '',
    install : true,
    install_dir : join_paths(get_option('libdir'), 'xorg/modules/drivers'))

install_data('conf/10-svr4ws.conf', install_dir : '/etc/X11/xorg.conf.d')