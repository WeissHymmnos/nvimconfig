call plug#begin('~/.vim/plugged')
Plug 'tpope/vim-sensible'
Plug 'fatih/vim-go', { 'tag': '*' }
Plug 'neoclide/coc.nvim', { 'branch': 'release' }
Plug 'preservim/nerdtree', { 'on': 'NERDTreeToggle' }
Plug 'tpope/vim-fireplace', { 'for': 'clojure' }
Plug 'junegunn/fzf', { 'dir': '~/.fzf', 'do': './install --all' }
call plug#end()
