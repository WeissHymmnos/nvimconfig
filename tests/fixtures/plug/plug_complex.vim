call plug#begin()
Plug 'kovisoft/paredit', { 'for': ['clojure', 'scheme'] }
Plug 'ycm-core/YouCompleteMe', { 'do': './install.py', 'frozen': 1 }
Plug 'junegunn/vim-easy-align', { 'on': ['<Plug>(EasyAlign)', 'EasyAlign'] }
Plug 'mbbill/undotree', { 'on': 'UndotreeToggle' }
call plug#end()
