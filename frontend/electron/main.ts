import { app, BrowserWindow, ipcMain, dialog, shell } from 'electron'
import path from 'path'
import { spawn, ChildProcess, execFile } from 'child_process'
import http from 'http'
import net from 'net'
import fs from 'fs'
import { pathToFileURL } from 'url'

const isDev = !app.isPackaged
const BACKEND_HOST = '127.0.0.1'
const BACKEND_PORT = 8299
const BACKEND_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}`

/** Resolve app icon path for BrowserWindow (works in dev & packaged) */
const APP_ICON = isDev
  ? path.join(__dirname, '..', 'resources', 'icon.png')
  : path.join(process.resourcesPath, 'icon.png')

let mainWindow: BrowserWindow | null = null
let splashWindow: BrowserWindow | null = null
let backendProcess: ChildProcess | null = null
let weOwnBackend = false   // true only if WE spawned the backend
let backendCrashCount = 0
const MAX_BACKEND_RESTARTS = 3

/* ------------------------------------------------------------------ */
/*  Path helpers                                                       */
/* ------------------------------------------------------------------ */

function getProjectRoot(): string {
  if (isDev) {
    return path.join(__dirname, '..', '..')
  }
  return process.resourcesPath
}

/* ------------------------------------------------------------------ */
/*  Backend lifecycle                                                  */
/* ------------------------------------------------------------------ */

/** Return true if something is already listening on the port */
function isPortInUse(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const sock = new net.Socket()
    sock.once('connect', () => { sock.destroy(); resolve(true) })
    sock.once('error', () => { sock.destroy(); resolve(false) })
    sock.connect(port, BACKEND_HOST)
  })
}

function isBackendHealthy(timeout = 2000): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(`${BACKEND_URL}/api/health`, (res) => {
      res.resume()
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(timeout, () => {
      req.destroy()
      resolve(false)
    })
  })
}

function getBackendPortPids(): Promise<number[]> {
  if (process.platform !== 'win32') return Promise.resolve([])

  return new Promise((resolve) => {
    execFile('netstat', ['-ano'], { windowsHide: true }, (err, stdout) => {
      if (err) {
        resolve([])
        return
      }

      const pids = new Set<number>()
      for (const line of stdout.split(/\r?\n/)) {
        if (!line.includes(`${BACKEND_HOST}:${BACKEND_PORT}`) || !line.includes('LISTENING')) continue
        const parts = line.trim().split(/\s+/)
        const pid = Number(parts[parts.length - 1])
        if (Number.isFinite(pid) && pid > 0) pids.add(pid)
      }
      resolve([...pids])
    })
  })
}

function killProcessTree(pid: number): Promise<void> {
  return new Promise((resolve) => {
    if (process.platform === 'win32') {
      execFile('taskkill', ['/pid', String(pid), '/f', '/t'], { windowsHide: true }, () => resolve())
    } else {
      try {
        process.kill(pid, 'SIGTERM')
      } catch { /* already gone */ }
      resolve()
    }
  })
}

async function clearUnhealthyBackendPort(): Promise<void> {
  const pids = await getBackendPortPids()
  if (!pids.length) return

  console.warn(`[Backend] Port ${BACKEND_PORT} is held by an unresponsive process; terminating PID(s): ${pids.join(', ')}`)
  await Promise.all(pids.map(killProcessTree))
  await new Promise(resolve => setTimeout(resolve, 1000))
}

async function spawnBackend(): Promise<void> {
  /* If the port is already occupied (e.g. manual uvicorn run), skip
     spawning and just connect to the existing process. */
  if (await isPortInUse(BACKEND_PORT)) {
    if (await isBackendHealthy()) {
      console.log('[Backend] Port already in use — attaching to healthy existing process')
      return
    }

    await clearUnhealthyBackendPort()

    if (await isPortInUse(BACKEND_PORT)) {
      if (await isBackendHealthy()) {
        console.log('[Backend] Existing backend recovered — attaching')
        return
      }
      throw new Error(`Port ${BACKEND_PORT} is occupied by an unresponsive process`)
    }
  }

  const projectRoot = getProjectRoot()

  const env: NodeJS.ProcessEnv = {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    HELIX_HOST: BACKEND_HOST,
    HELIX_PORT: String(BACKEND_PORT),
    HELIX_TOOLS_DIR: path.join(projectRoot, 'tools'),
    HELIX_WORKSPACE_DIR: getWorkspacePath(),
  }

  /* Only point BABEL_DATADIR at the bundled data directory when it exists.
     A PATH-resolved Open Babel (conda-forge, distro package) finds its own data
     relative to its install prefix, and an invalid override breaks plugin loading. */
  const bundledBabelData = path.join(projectRoot, 'tools', 'OpenBabel', 'data')
  if (fs.existsSync(bundledBabelData)) {
    env.BABEL_DATADIR = bundledBabelData
  } else {
    delete env.BABEL_DATADIR
  }

  weOwnBackend = true

  if (isDev) {
    /* Dev mode — run Python directly */
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3'
    const backendArgs = [
      '-m', 'uvicorn', 'backend.main:app',
      '--host', BACKEND_HOST,
      '--port', String(BACKEND_PORT),
    ]
    /* A reloader is useful during interactive development, but it creates a
       second process that can outlive Electron during Playwright teardown.
       E2E launches the already-built frontend, so there is nothing to reload. */
    if (!process.env.HELIX_E2E_TESTING) backendArgs.push('--reload')

    backendProcess = spawn(
      pythonCmd,
      backendArgs,
      {
        cwd: projectRoot,
        env,
        stdio: ['ignore', 'pipe', 'pipe'],
        /* No shell is required for an executable plus an argument array.
           Keeping the Python process as the direct child makes SIGTERM target
           the backend itself instead of an intermediate shell. */
        shell: false,
        windowsHide: true,
      }
    )
  } else {
    /* Production — launch the PyInstaller-bundled backend binary */
    const backendExe = path.join(
      projectRoot,
      'backend',
      process.platform === 'win32' ? 'backend.exe' : 'backend'
    )
    backendProcess = spawn(backendExe, [], {
      cwd: path.join(projectRoot, 'backend'),
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    })
  }

  /* Noise filter — suppress repetitive uvicorn access-log lines for
     polling endpoints so the kernel dock stays useful. */
  const isNoisy = (line: string) =>
    /"GET \/api\/(health|system\/stats|jobs\/current)/.test(line) ||
    /to-Python converter for class boost::shared_ptr<class RDKit::FilterHierarchyMatcher> already registered/.test(line)

  backendProcess.stdout?.on('data', (data: Buffer) => {
    const msg = data.toString().trim()
    if (msg && !isNoisy(msg)) sendToRenderer('backend:log', msg)
  })

  backendProcess.stderr?.on('data', (data: Buffer) => {
    const msg = data.toString().trim()
    if (msg && !isNoisy(msg)) sendToRenderer('backend:log', msg)
  })

  backendProcess.on('error', (err) => {
    console.error('[Backend] Failed to start:', err.message)
    sendToRenderer('backend:error', err.message)
  })

  backendProcess.on('exit', (code) => {
    console.log(`[Backend] Exited with code ${code}`)
    backendProcess = null

    // Auto-restart if crashed unexpectedly and we own the process
    if (weOwnBackend && code !== 0 && code !== null) {
      backendCrashCount++
      if (backendCrashCount <= MAX_BACKEND_RESTARTS) {
        const delay = Math.pow(2, backendCrashCount) * 1000 // 2s, 4s, 8s
        console.log(`[Backend] Restarting in ${delay}ms (attempt ${backendCrashCount}/${MAX_BACKEND_RESTARTS})`)
        sendToRenderer('backend:restarting', backendCrashCount)
        setTimeout(async () => {
          try {
            await spawnBackend()
            const healthy = await pollBackendHealth(15, 1000)
            if (healthy) {
              console.log('[Backend] Restart successful')
            }
          } catch (err) {
            console.error('[Backend] Restart failed:', err)
          }
        }, delay)
      } else {
        console.error('[Backend] Max restart attempts reached')
        sendToRenderer('backend:fatal', `Backend crashed ${backendCrashCount} times. Please restart the application.`)
      }
    }
  })
}

function pollBackendHealth(retries = 30, interval = 1000): Promise<boolean> {
  return new Promise((resolve) => {
    let attempts = 0
    let settled = false

    const check = () => {
      if (settled) return
      attempts++
      const req = http.get(`${BACKEND_URL}/api/health`, (res) => {
        if (settled) return
        if (res.statusCode === 200) {
          settled = true
          console.log('[Backend] Health check passed')
          sendToRenderer('backend:ready', true)
          resolve(true)
        } else {
          retry()
        }
      })

      req.on('error', () => {
        if (!settled) retry()
      })
      req.setTimeout(2000, () => {
        req.destroy()
        /* destroy emits 'error' which already calls retry() */
      })
    }

    const retry = () => {
      if (settled) return
      if (attempts >= retries) {
        settled = true
        console.error('[Backend] Health check failed after max retries')
        sendToRenderer('backend:error', 'Backend failed to start within expected time')
        resolve(false)
      } else {
        setTimeout(check, interval)
      }
    }

    check()
  })
}

function killBackend(): void {
  if (!backendProcess || !weOwnBackend) return
  const processToStop = backendProcess
  /* Mark this as an intentional shutdown before signalling. Otherwise a
     platform-specific non-zero exit code can enter the crash-restart path
     while Electron is already quitting. */
  backendProcess = null
  weOwnBackend = false

  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(processToStop.pid), '/f', '/t'], {
        shell: false,
        windowsHide: true,
        stdio: 'ignore',
      })
    } else {
      processToStop.kill('SIGTERM')
      /* Give uvicorn a bounded graceful window, then guarantee the child
         cannot keep Playwright's worker alive through inherited pipe handles. */
      const forceKill = setTimeout(() => {
        if (processToStop.exitCode === null && processToStop.signalCode === null) {
          try { processToStop.kill('SIGKILL') } catch { /* already gone */ }
        }
      }, 3000)
      forceKill.unref()
      processToStop.once('exit', () => clearTimeout(forceKill))
    }
  } catch (err) {
    console.error('[Backend] Error killing process:', err)
  }
}

/* ------------------------------------------------------------------ */
/*  Splash screen                                                      */
/* ------------------------------------------------------------------ */

function createSplash(): void {
  splashWindow = new BrowserWindow({
    width: 420,
    height: 340,
    frame: false,
    transparent: false,
    resizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    backgroundColor: '#0f1117',
    icon: APP_ICON,
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  splashWindow.loadFile(
    isDev
      ? path.join(__dirname, '..', 'electron', 'splash.html')
      : path.join(__dirname, 'splash.html')
  )
  splashWindow.once('ready-to-show', () => splashWindow?.show())
  splashWindow.on('closed', () => { splashWindow = null })
}

function closeSplash(): void {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.close()
  }
  splashWindow = null
}

/* ------------------------------------------------------------------ */
/*  Window creation                                                    */
/* ------------------------------------------------------------------ */

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    frame: false,
    titleBarStyle: 'hidden',
    backgroundColor: '#0f1117',
    icon: APP_ICON,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  mainWindow.once('ready-to-show', () => {
    closeSplash()
    mainWindow?.show()
  })

  mainWindow.on('maximize', () => {
    mainWindow?.webContents.send('window:maximize-change', true)
  })

  mainWindow.on('unmaximize', () => {
    mainWindow?.webContents.send('window:maximize-change', false)
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    try {
      const target = new URL(url)
      if (target.protocol === 'https:' || target.protocol === 'http:') {
        void shell.openExternal(target.toString())
      }
    } catch {
      // Ignore malformed or non-web targets.
    }
    return { action: 'deny' }
  })

  /* Electron's initial loadFile() is a file:// navigation too. Allow only
     the exact renderer entry point; every other navigation remains blocked
     and external web links continue through the explicit shell handler above. */
  const appEntryUrl = pathToFileURL(
    path.join(__dirname, '..', 'dist', 'index.html'),
  ).toString()
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (url === appEntryUrl || url.startsWith(`${appEntryUrl}#`)) return
    event.preventDefault()
    try {
      const target = new URL(url)
      if (target.protocol === 'https:' || target.protocol === 'http:') {
        void shell.openExternal(target.toString())
      }
    } catch {
      // Ignore malformed or non-web targets.
    }
  })

  if (isDev && process.env['VITE_DEV_SERVER_URL']) {
    mainWindow.loadURL(process.env['VITE_DEV_SERVER_URL'])
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }
}

/* ------------------------------------------------------------------ */
/*  Workspace path management                                          */
/* ------------------------------------------------------------------ */

function getAppDataDir(): string {
  const home = require('os').homedir()
  let base: string
  if (process.platform === 'win32') {
    base = process.env.APPDATA || path.join(home, 'AppData', 'Roaming')
  } else if (process.platform === 'darwin') {
    base = path.join(home, 'Library', 'Application Support')
  } else {
    /* Linux and other POSIX — matches backend/utils/guard.py */
    base = process.env.XDG_DATA_HOME || path.join(home, '.local', 'share')
  }
  const dir = path.join(base, 'HelixCore')
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
  return dir
}

function getWorkspaceConfigPath(): string {
  return path.join(getAppDataDir(), 'workspace.json')
}

/** True when running as an electron-builder portable exe */
function isPortable(): boolean {
  return !!process.env.PORTABLE_EXECUTABLE_DIR
}

/**
 * Resolve the workspace root directory.
 *
 * Priority:
 * 1. Saved user choice from workspace.json
 * 2. Portable exe → HelixCoreWorkspace/ next to the .exe
 * 3. Installed / dev → %APPDATA%/HelixCore/workspace
 */
function getWorkspaceRoot(): string {
  // Check saved config first
  const configPath = getWorkspaceConfigPath()
  if (fs.existsSync(configPath)) {
    try {
      const cfg = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      if (cfg.workspace && fs.existsSync(cfg.workspace)) {
        return cfg.workspace
      }
    } catch { /* fall through to default */ }
  }

  // Portable exe: create HelixCoreWorkspace next to the exe
  if (isPortable()) {
    const portableDir = process.env.PORTABLE_EXECUTABLE_DIR!
    const ws = path.join(portableDir, 'HelixCoreWorkspace')
    if (!fs.existsSync(ws)) fs.mkdirSync(ws, { recursive: true })
    return ws
  }

  // Installed / dev fallback
  const defaultWs = path.join(getAppDataDir(), 'workspace')
  if (!fs.existsSync(defaultWs)) fs.mkdirSync(defaultWs, { recursive: true })
  return defaultWs
}

/** Legacy alias used by the backend env var */
function getWorkspacePath(): string {
  return getWorkspaceRoot()
}

function saveWorkspaceConfig(workspacePath: string): void {
  const configPath = getWorkspaceConfigPath()
  fs.writeFileSync(configPath, JSON.stringify({ workspace: workspacePath }, null, 2), 'utf-8')
  // Also set for the current backend session
  process.env.HELIX_WORKSPACE_DIR = workspacePath
}

/* ------------------------------------------------------------------ */
/*  IPC handlers                                                       */
/* ------------------------------------------------------------------ */

function registerIPC(): void {
  ipcMain.on('window:minimize', () => mainWindow?.minimize())
  ipcMain.on('window:maximize', () => {
    if (mainWindow?.isMaximized()) {
      mainWindow.unmaximize()
    } else {
      mainWindow?.maximize()
    }
  })
  ipcMain.on('window:close', () => mainWindow?.close())

  ipcMain.handle('window:is-maximized', () => mainWindow?.isMaximized() ?? false)

  ipcMain.handle('dialog:open-file', async (_event, filters) => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ['openFile'],
      filters: filters || [{ name: 'All Files', extensions: ['*'] }],
    })
    return result.canceled ? null : result.filePaths[0]
  })

  ipcMain.handle('dialog:open-directory', async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ['openDirectory'],
    })
    return result.canceled ? null : result.filePaths[0]
  })

  ipcMain.handle('app:version', () => app.getVersion())
  ipcMain.handle('app:platform', () => process.platform)
  ipcMain.handle('app:base-path', () => getProjectRoot())

  ipcMain.on('shell:show-item-in-folder', (_event, fullPath: string) => {
    shell.showItemInFolder(fullPath)
  })

  /* Workspace root — used by useWorkspace to build subfolder paths */
  ipcMain.handle('app:get-workspace-root', () => {
    return getWorkspaceRoot()
  })

  /* Workspace validation — check existence, writability, auto-create subdirs */
  ipcMain.handle('workspace:validate', (_event, wsPath: string) => {
    const subfolders = [
      'fetched_pdb', 'ligands_3d', 'minimized', 'converted_pdbqt',
      'docking_results', 'oracle_predictions', 'results', 'pipeline_output', 'projects',
    ]
    try {
      if (!fs.existsSync(wsPath)) {
        fs.mkdirSync(wsPath, { recursive: true })
      }
      // Test write access
      fs.accessSync(wsPath, fs.constants.W_OK)
      // Ensure all subdirectories exist
      for (const sub of subfolders) {
        const p = path.join(wsPath, sub)
        if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true })
      }
      return { valid: true }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      return { valid: false, error: msg }
    }
  })

  /* First-run workspace chooser */
  ipcMain.handle('app:get-workspace', () => {
    return getWorkspacePath()
  })

  ipcMain.handle('app:set-workspace', async (_event, customPath?: string) => {
    let selected = customPath
    if (!selected) {
      const result = await dialog.showOpenDialog(mainWindow!, {
        title: 'Choose Workspace Directory',
        properties: ['openDirectory', 'createDirectory'],
        buttonLabel: 'Select Workspace',
      })
      if (result.canceled) return null
      selected = result.filePaths[0]
    }
    if (selected) {
      saveWorkspaceConfig(selected)
      return selected
    }
    return null
  })
}

/* ------------------------------------------------------------------ */
/*  Utility — buffered IPC                                             */
/* ------------------------------------------------------------------ */

let rendererReady = false
const pendingIPC: Array<{ channel: string; args: unknown[] }> = []

function sendToRenderer(channel: string, ...args: unknown[]): void {
  if (!mainWindow || !rendererReady) {
    pendingIPC.push({ channel, args })
    return
  }
  mainWindow.webContents.send(channel, ...args)
}

function flushPendingIPC(): void {
  rendererReady = true
  for (const { channel, args } of pendingIPC) {
    mainWindow?.webContents.send(channel, ...args)
  }
  pendingIPC.length = 0
}

/* ------------------------------------------------------------------ */
/*  App lifecycle                                                      */
/* ------------------------------------------------------------------ */

app.whenReady().then(async () => {
  registerIPC()
  createSplash()
  await spawnBackend()
  createWindow()

  /* Wait for the renderer page to fully load so React IPC listeners
     are registered before we start sending backend status events. */
  if (mainWindow) {
    await new Promise<void>((resolve) => {
      if (mainWindow!.webContents.isLoading()) {
        mainWindow!.webContents.once('did-finish-load', () => {
          /* Small extra delay to let React useEffect hooks register */
          setTimeout(() => { flushPendingIPC(); resolve() }, 300)
        })
      } else {
        flushPendingIPC()
        resolve()
      }
    })
  }

  await pollBackendHealth()

  /* Periodic health watchdog — detect silent backend crashes */
  let consecutiveFailures = 0
  setInterval(() => {
    if (!weOwnBackend || !mainWindow) return
    const req = http.get(`${BACKEND_URL}/api/health`, (res) => {
      if (res.statusCode === 200) {
        consecutiveFailures = 0
      } else {
        consecutiveFailures++
      }
    })
    req.on('error', () => {
      consecutiveFailures++
      if (consecutiveFailures >= 3 && !backendProcess) {
        console.log('[Watchdog] Backend appears down, triggering restart')
        consecutiveFailures = 0
        backendCrashCount++
        if (backendCrashCount <= MAX_BACKEND_RESTARTS) {
          sendToRenderer('backend:restarting', backendCrashCount)
          spawnBackend().then(() => pollBackendHealth(15, 1000))
        } else {
          sendToRenderer('backend:fatal', 'Backend is unresponsive. Please restart the application.')
        }
      }
    })
    req.setTimeout(5000, () => req.destroy())
  }, 30000)
})

app.on('window-all-closed', () => {
  killBackend()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  killBackend()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})
