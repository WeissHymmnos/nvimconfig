if vim.g.loaded_ucdp_bridge == 1 then
  return
end
vim.g.loaded_ucdp_bridge = 1

require("ucdp_bridge").setup()
