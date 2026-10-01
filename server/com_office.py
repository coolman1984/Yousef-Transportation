"""Trip Orders - reading files THROUGH Microsoft Excel / Word installed on this PC (COM automation, via PowerShell).

Why: some company files are protected by a document-security (DRM) system. No other program can read them, but the Office program
on a PC where the company's security agent is installed opens them normally - the agent decrypts for Office, as it does for the user.
This module asks Office to open the file read-only (macros off, no windows, nothing saved) and hands back the cell values / the text.
It does not touch or bypass any protection: if Office cannot open the file, neither can we, and the person is told so.

Only the values are copied out (as JSON in a private temp folder that is removed afterwards); no decrypted copy of the file is written.
Works only on Windows with Excel / Word installed, and only for the person who is logged in to that PC (Office needs a desktop session).
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile

import xlsx_read
from xlsx_read import Cell, Sheet, Workbook

TIMEOUT = 180
WORD_EXT = {'doc', 'docx', 'docm', 'dotx', 'dotm', 'rtf', 'odt', 'wps', 'txt', 'htm', 'html'}
SHEET_EXT = {'xls', 'xlsx', 'xlsm', 'xlsb', 'xltx', 'xltm', 'ods', 'csv', 'tsv', 'xml', 'et'}
MAX_CELLS = 1_500_000


class OfficeError(Exception):
    """Office could not read the file; the message says why, in plain words."""


# --------------------------------------------------------------------------- is Office here?
def _progid_registered(progid):
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + '\\CLSID'))
        return True
    except (ImportError, OSError):
        return False


def _powershell():
    for c in (shutil.which('powershell'), os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')):
        if c and os.path.exists(c):
            return c
    return None


def available(app):
    """app: 'excel' or 'word'."""
    if sys.platform != 'win32' or not _powershell():
        return False
    return _progid_registered('Excel.Application' if app == 'excel' else 'Word.Application')


def kind_of_name(name):
    ext = name.rsplit('.', 1)[-1].lower() if '.' in (name or '') else ''
    return 'word' if ext in WORD_EXT else 'sheet' if ext in SHEET_EXT else None


# --------------------------------------------------------------------------- the PowerShell scripts (values go out as JSON)
_COMMON = r'''
$ErrorActionPreference = 'Stop'
$inp = $env:TO_IN
$out = $env:TO_OUT
function E([string]$s) {
  $s = $s.Replace('\', '\\').Replace('"', '\"').Replace("`r", '\r').Replace("`n", '\n').Replace("`t", '\t')
  return [regex]::Replace($s, '[\x00-\x1f]', { param($m) '\u{0:x4}' -f [int][char]$m.Value })
}
function Done($text) {
  [System.IO.File]::WriteAllText($out, $text, (New-Object System.Text.UTF8Encoding $false))
}
function Fail($msg) {
  Done ('{"error":"' + (E ([string]$msg)) + '"}')
}
$inv = [System.Globalization.CultureInfo]::InvariantCulture
'''

EXCEL_SCRIPT = _COMMON + r'''
function V($x) {
  if ($x -eq $null) { return 'null' }
  if ($x -is [string]) { return '"' + (E $x) + '"' }
  if ($x -is [bool]) { if ($x) { return 'true' } else { return 'false' } }
  if ($x -is [datetime]) { return '{"d":' + $x.ToOADate().ToString('R', $inv) + '}' }
  if ($x -is [int] -and $x -lt -2000000000) { return 'null' }
  if ($x -is [double] -or $x -is [int] -or $x -is [decimal] -or $x -is [long] -or $x -is [single] -or $x -is [int16]) { return ([Convert]::ToDouble($x)).ToString('R', $inv) }
  return '"' + (E ([string]$x)) + '"'
}
$xl = $null
$wb = $null
try {
  $xl = New-Object -ComObject Excel.Application
  $xl.Visible = $false
  $xl.DisplayAlerts = $false
  $xl.AskToUpdateLinks = $false
  $xl.EnableEvents = $false
  try { $xl.AutomationSecurity = 3 } catch { }
  $wb = $xl.Workbooks.Open($inp, 0, $true)
  $sb = New-Object System.Text.StringBuilder
  [void]$sb.Append('{"date1904":' + $(if ($wb.Date1904) { 'true' } else { 'false' }) + ',"sheets":[')
  $firstSheet = $true
  $total = 0
  foreach ($ws in $wb.Worksheets) {
    $rng = $ws.UsedRange
    $r0 = [int]$rng.Row
    $c0 = [int]$rng.Column
    try { $v = $rng.Value } catch { $v = $rng.Value2 }
    if (-not $firstSheet) { [void]$sb.Append(',') }
    $firstSheet = $false
    $hidden = ([int]$ws.Visible -ne -1)
    [void]$sb.Append('{"name":"' + (E ([string]$ws.Name)) + '","hidden":' + $(if ($hidden) { 'true' } else { 'false' }) + ',"row0":' + $r0 + ',"col0":' + $c0 + ',"rows":[')
    if ($v -is [System.Array]) {
      $lb0 = $v.GetLowerBound(0); $ub0 = $v.GetUpperBound(0)
      $lb1 = $v.GetLowerBound(1); $ub1 = $v.GetUpperBound(1)
      $total += ($ub0 - $lb0 + 1) * ($ub1 - $lb1 + 1)
      if ($total -gt 1500000) { throw 'The workbook is too large to import safely.' }
      for ($i = $lb0; $i -le $ub0; $i++) {
        if ($i -gt $lb0) { [void]$sb.Append(',') }
        [void]$sb.Append('[')
        for ($j = $lb1; $j -le $ub1; $j++) {
          if ($j -gt $lb1) { [void]$sb.Append(',') }
          [void]$sb.Append((V ($v[$i, $j])))
        }
        [void]$sb.Append(']')
      }
    } else {
      [void]$sb.Append('[' + (V $v) + ']')
    }
    [void]$sb.Append(']}')
  }
  [void]$sb.Append(']}')
  Done $sb.ToString()
} catch {
  Fail $_.Exception.Message
} finally {
  try { if ($wb) { $wb.Close($false) } } catch { }
  try { if ($xl) { $xl.Quit() } } catch { }
  try { if ($wb) { [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($wb) } } catch { }
  try { if ($xl) { [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($xl) } } catch { }
  [GC]::Collect()
}
'''

WORD_SCRIPT = _COMMON + r'''
function Clean($t) { return ([string]$t).TrimEnd([char]13, [char]7).Trim() }
$wd = $null
$doc = $null
try {
  $wd = New-Object -ComObject Word.Application
  $wd.Visible = $false
  $wd.DisplayAlerts = 0
  try { $wd.AutomationSecurity = 3 } catch { }
  $doc = $wd.Documents.Open($inp, $false, $true, $false)
  $paras = New-Object System.Collections.Generic.List[string]
  $n = 0
  foreach ($p in $doc.Paragraphs) {
    $n++
    if ($n -gt 6000) { break }
    $inTable = $false
    try { $inTable = [bool]$p.Range.Information(12) } catch { }
    if (-not $inTable) {
      $t = Clean $p.Range.Text
      if ($t) { $paras.Add($t) }
    }
  }
  try {
    foreach ($s in $doc.Shapes) {
      try { if ($s.TextFrame.HasText) { $t = Clean $s.TextFrame.TextRange.Text; if ($t) { $paras.Add($t) } } } catch { }
    }
  } catch { }
  $tables = New-Object System.Text.StringBuilder
  [void]$tables.Append('[')
  $firstT = $true
  foreach ($tb in $doc.Tables) {
    $rows = @{}
    $maxRow = 0
    foreach ($c in $tb.Range.Cells) {
      $ri = [int]$c.RowIndex
      if (-not $rows.ContainsKey($ri)) { $rows[$ri] = New-Object System.Collections.Generic.List[string] }
      $rows[$ri].Add((Clean $c.Range.Text))
      if ($ri -gt $maxRow) { $maxRow = $ri }
    }
    if (-not $firstT) { [void]$tables.Append(',') }
    $firstT = $false
    [void]$tables.Append('[')
    for ($r = 1; $r -le $maxRow; $r++) {
      if ($r -gt 1) { [void]$tables.Append(',') }
      [void]$tables.Append('[')
      if ($rows.ContainsKey($r)) {
        $cells = $rows[$r]
        for ($k = 0; $k -lt $cells.Count; $k++) {
          if ($k -gt 0) { [void]$tables.Append(',') }
          [void]$tables.Append('"' + (E $cells[$k]) + '"')
        }
      }
      [void]$tables.Append(']')
    }
    [void]$tables.Append(']')
  }
  [void]$tables.Append(']')
  $pj = ($paras | ForEach-Object { '"' + (E $_) + '"' }) -join ','
  Done ('{"paragraphs":[' + $pj + '],"tables":' + $tables.ToString() + '}')
} catch {
  Fail $_.Exception.Message
} finally {
  try { if ($doc) { $doc.Close(0) } } catch { }
  try { if ($wd) { $wd.Quit(0) } } catch { }
  try { if ($doc) { [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc) } } catch { }
  try { if ($wd) { [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($wd) } } catch { }
  [GC]::Collect()
}
'''


# --------------------------------------------------------------------------- running it
def _run(app, data, name, tmp_root=None, runner=None):
    """Returns the parsed JSON the script wrote. runner(cmd, env, timeout) can be replaced in tests."""
    ext = (name.rsplit('.', 1)[-1].lower() if '.' in (name or '') else '') or ('xlsx' if app == 'excel' else 'docx')
    ext = ''.join(ch for ch in ext if ch.isalnum())[:5] or 'tmp'
    if tmp_root:
        os.makedirs(tmp_root, exist_ok=True)
    work = tempfile.mkdtemp(prefix='office-', dir=tmp_root)
    try:
        src, out, ps1 = (os.path.join(work, 'in.' + ext), os.path.join(work, 'out.json'), os.path.join(work, 'run.ps1'))
        with open(src, 'wb') as f:
            f.write(data)
        with open(ps1, 'w', encoding='utf-8-sig') as f:       # the BOM makes Windows PowerShell read it as UTF-8
            f.write(EXCEL_SCRIPT if app == 'excel' else WORD_SCRIPT)
        exe = _powershell()
        cmd = [exe or 'powershell', '-NoProfile', '-NonInteractive', '-STA', '-ExecutionPolicy', 'Bypass', '-File', ps1]
        env = {**os.environ, 'TO_IN': src, 'TO_OUT': out}
        try:
            (runner or _subprocess_runner)(cmd, env, TIMEOUT)
        except subprocess.TimeoutExpired:
            raise OfficeError(f'Microsoft {"Excel" if app == "excel" else "Word"} took too long to open this file. Close any open Office windows and try again.')
        except OSError as e:
            raise OfficeError('Microsoft Office could not be started on this PC: ' + str(e))
        if not os.path.exists(out):
            raise OfficeError(f'Microsoft {"Excel" if app == "excel" else "Word"} did not give an answer. Is it installed and working for the logged-in user?')
        with open(out, 'rb') as f:
            raw = f.read()
        try:
            res = json.loads(raw.decode('utf-8-sig'))
        except ValueError:
            raise OfficeError('Microsoft Office gave an answer that could not be understood.')
        if isinstance(res, dict) and res.get('error'):
            raise OfficeError(_friendly(res['error'], app))
        return res
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _subprocess_runner(cmd, env, timeout):
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    subprocess.run(cmd, env=env, timeout=timeout, creationflags=flags, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _friendly(msg, app):
    low = msg.lower()
    nm = 'Excel' if app == 'excel' else 'Word'
    if 'password' in low:
        return f'The file is protected with a password. Open it in {nm}, remove the password and save a copy.'
    if 'too large' in low:
        return msg
    if 'class not registered' in low or '80040154' in low:
        return f'Microsoft {nm} is not installed on this PC.'
    if 'cannot access' in low or 'could not find' in low or "couldn't find" in low:
        return f'Microsoft {nm} could not open the file: {msg[:160]}'
    return f'Microsoft {nm} could not open this file ({msg[:160]}). If your company protects its documents, make sure the security program is running on this PC and you are allowed to open the file.'


# --------------------------------------------------------------------------- JSON -> the shapes the rest of the program reads
def workbook_from_json(d):
    d1904 = bool(d.get('date1904'))
    sheets = []
    for s in d.get('sheets', []):
        sh = Sheet(s.get('name') or 'Sheet', hidden=bool(s.get('hidden')))
        r0, c0 = int(s.get('row0') or 1), int(s.get('col0') or 1)
        for i, row in enumerate(s.get('rows') or []):
            for j, v in enumerate(row):
                if isinstance(v, dict) and 'd' in v:
                    num = float(v['d'])
                    v = xlsx_read.excel_date(num, d1904)
                    if isinstance(v, dt.datetime) and num < 1:
                        v = v.time()
                elif isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
                    v = int(v)
                if v is not None and v != '':
                    sh.cells[(r0 + i, c0 + j)] = Cell(v)
        if sh.cells:
            sh.max_row = max(a for a, _ in sh.cells)
            sh.max_col = max(b for _, b in sh.cells)
        sheets.append(sh)
    if not sheets:
        raise OfficeError('Microsoft Excel opened the file but found no sheets in it.')
    return Workbook(sheets, d1904)


def document_from_json(d):
    return {'paragraphs': [str(p) for p in d.get('paragraphs', [])],
            'tables': [[[str(c) for c in row] for row in t] for t in d.get('tables', [])]}


def read_workbook(data, name='', tmp_root=None, runner=None):
    return workbook_from_json(_run('excel', data, name, tmp_root, runner))


def read_document(data, name='', tmp_root=None, runner=None):
    return document_from_json(_run('word', data, name, tmp_root, runner))
