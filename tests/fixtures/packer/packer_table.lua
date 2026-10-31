use {
  'lewis6991/gitsigns.nvim',
  requires = { 'nvim-lua/plenary.nvim' },
  branch = 'main',
  opt = true,
  event = 'BufRead',
}
use {
  'nvim-telescope/telescope.nvim',
  tag = '0.1.x',
  requires = { {'nvim-lua/plenary.nvim'} }
}
