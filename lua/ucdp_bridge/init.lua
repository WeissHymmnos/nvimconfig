local M = { _channel = nil }

local function schema_path()
  return vim.fn.stdpath("cache") .. "/ucdp-bridge/options.json"
end

function M.export_schema()
  local ok, result = pcall(function()
    local options = {}
    for name, info in pairs(vim.api.nvim_get_all_options_info()) do
      options[#options + 1] = {
        name = info.name or name,
        type = info.type,
        default = info.default,
        scope = info.scope,
        shortname = info.shortname,
      }
    end
    table.sort(options, function(a, b)
      return a.name < b.name
    end)

    local path = schema_path()
    vim.fn.mkdir(vim.fn.fnamemodify(path, ":h"), "p")
    vim.fn.writefile({ vim.json.encode({ options = options }) }, path)
    return path
  end)
  if ok then
    return result
  end
  return nil, result
end

local function daemon_socket()
  if vim.env.UCDP_DAEMON_SOCKET and vim.env.UCDP_DAEMON_SOCKET ~= "" then
    return vim.env.UCDP_DAEMON_SOCKET
  end
  if vim.env.XDG_RUNTIME_DIR and vim.env.XDG_RUNTIME_DIR ~= "" then
    return vim.env.XDG_RUNTIME_DIR .. "/ucdp-bridge/daemon.sock"
  end
  local ok, uid = pcall(vim.loop.getuid)
  return "/tmp/ucdp-bridge-" .. (ok and uid or vim.env.UID or "unknown") .. "/daemon.sock"
end

function M.close()
  if M._channel then
    pcall(vim.fn.chanclose, M._channel)
    M._channel = nil
  end
end

function M.connect()
  if M._channel then
    return M._channel
  end
  local ok, channel = pcall(vim.fn.sockconnect, "pipe", daemon_socket(), { rpc = true })
  if not ok or not channel or channel == 0 then
    return nil
  end
  M._channel = channel
  pcall(vim.fn.rpcnotify, channel, "ucdp_register", {
    socket = vim.v.servername,
    config = vim.fn.stdpath("config"),
    schema = schema_path(),
  })
  return channel
end

function M.setup()
  vim.opt.autoread = true
  M.export_schema()

  vim.api.nvim_create_user_command("UcdpExportSchema", function()
    local path, err = M.export_schema()
    if path then
      vim.notify("UCDP schema exported to " .. path)
    else
      vim.notify("UCDP schema export failed: " .. tostring(err), vim.log.levels.ERROR)
    end
  end, { desc = "Export Neovim option schema for UCDP" })

  local group = vim.api.nvim_create_augroup("UcdpBridge", { clear = true })
  M._group = group

  vim.api.nvim_create_autocmd("BufWritePost", {
    group = group,
    pattern = "*.lua",
    callback = function(args)
      if not M._channel then
        return
      end
      local config = vim.fn.fnamemodify(vim.fn.stdpath("config"), ":p"):gsub("/+$", "")
      local path = vim.fn.fnamemodify(args.file, ":p")
      if path:sub(1, #config + 1) == config .. "/" then
        pcall(vim.fn.rpcnotify, M._channel, "ucdp_buf_written", path)
      end
    end,
  })

  vim.api.nvim_create_autocmd("FocusGained", {
    group = group,
    callback = function()
      M.connect()
      pcall(vim.cmd, "silent! checktime")
    end,
  })

  vim.api.nvim_create_autocmd("CursorHold", {
    group = group,
    callback = function()
      pcall(vim.cmd, "silent! checktime")
    end,
  })

  vim.api.nvim_create_autocmd("VimLeavePre", {
    group = group,
    callback = M.close,
  })

  M.connect()
end

return M
