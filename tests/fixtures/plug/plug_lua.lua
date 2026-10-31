local Plug = vim.fn['plug#']

vim.call('plug#begin')
Plug('junegunn/seoul256.vim')
Plug('fatih/vim-go', { ['tag'] = '*' })
Plug('preservim/nerdtree', { ['on'] = 'NERDTreeToggle' })
Plug('tpope/vim-fireplace', { ['for'] = 'clojure' })
Plug('junegunn/fzf', { ['dir'] = '~/.fzf', ['do'] = './install --all' })
Plug('~/my-prototype-plugin')
vim.call('plug#end')
