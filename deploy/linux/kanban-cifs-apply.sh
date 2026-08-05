#!/usr/bin/env bash
# 台账 CIFS 凭据应用（3.7.15 B）· 受控接口
# 用途：写 cred（0600）+ 可选 remount。仅允许固定参数，禁止任意 shell。
# 安装：sudo install -m 755 deploy/linux/kanban-cifs-apply.sh /usr/local/sbin/kanban-cifs-apply
# sudoers：见 deploy/linux/sudoers.d-kanban-cifs
set -euo pipefail

CRED_FILE=""
USERNAME=""
PASSWORD=""
HAVE_PASSWORD=0
SERVER=""
SHARE=""
MOUNT_ROOT="/mnt/kanban-ledger"
DRY_RUN=0
SKIP_MOUNT=0

usage() {
  echo "用法: $0 --cred-file PATH --username U [--password-from-env|--password P] [--server S] [--share SH] [--mount-root M] [--dry-run] [--skip-mount]" >&2
  echo "  密码优先：--password-from-env 读 KANBAN_CIFS_PASSWORD（SEC-001 禁止 argv 明文）" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cred-file) CRED_FILE="${2:-}"; shift 2 ;;
    --username) USERNAME="${2:-}"; shift 2 ;;
    # SEC-001：推荐 env 通道；--password 仍兼容但会进 argv（勿在生产新代码使用）
    --password-from-env)
      PASSWORD="${KANBAN_CIFS_PASSWORD:-}"
      HAVE_PASSWORD=1
      shift
      ;;
    --password) PASSWORD="${2:-}"; HAVE_PASSWORD=1; shift 2 ;;
    --server) SERVER="${2:-}"; shift 2 ;;
    --share) SHARE="${2:-}"; shift 2 ;;
    --mount-root) MOUNT_ROOT="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --skip-mount) SKIP_MOUNT=1; shift ;;
    -h|--help) usage ;;
    *) echo "未知参数: $1" >&2; usage ;;
  esac
done

if [[ -z "$CRED_FILE" ]]; then
  echo "缺少 --cred-file" >&2
  exit 2
fi
if [[ -z "$USERNAME" && "$HAVE_PASSWORD" -eq 0 ]]; then
  echo "须提供 --username 或 --password-from-env/--password" >&2
  exit 2
fi

# 读旧密码（改 username 且未传 password 时保留）
OLD_PW=""
OLD_USER=""
if [[ -f "$CRED_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      username=*) OLD_USER="${line#username=}" ;;
      password=*) OLD_PW="${line#password=}" ;;
    esac
  done <"$CRED_FILE"
fi

FINAL_USER="${USERNAME:-$OLD_USER}"
if [[ "$HAVE_PASSWORD" -eq 1 ]]; then
  FINAL_PW="$PASSWORD"
else
  FINAL_PW="$OLD_PW"
fi

if [[ -z "$FINAL_USER" ]]; then
  echo "账号为空，拒绝写凭据" >&2
  exit 1
fi

write_cred() {
  local target="$1"
  local dir
  dir=$(dirname "$target")
  mkdir -p "$dir"
  local tmp
  tmp=$(mktemp "${dir}/.cifs-cred.XXXXXX")
  # 不 echo 密码到进程列表外：heredoc
  {
    printf 'username=%s\n' "$FINAL_USER"
    printf 'password=%s\n' "$FINAL_PW"
  } >"$tmp"
  chmod 600 "$tmp"
  # 备份旧文件
  if [[ -f "$target" ]]; then
    cp -a "$target" "${target}.bak" 2>/dev/null || true
    chmod 600 "${target}.bak" 2>/dev/null || true
  fi
  mv -f "$tmp" "$target"
  chmod 600 "$target"
}

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "dry-run: would write cred to $CRED_FILE user=${FINAL_USER} (password redacted)"
  exit 0
fi

write_cred "$CRED_FILE"
echo "cred_ok path=$CRED_FILE"

if [[ "$SKIP_MOUNT" -eq 1 ]]; then
  echo "skip_mount"
  exit 0
fi

# 幂等 remount：已挂载则 mount -o remount；否则 mount
if findmnt -n "$MOUNT_ROOT" >/dev/null 2>&1; then
  if mount -o remount "$MOUNT_ROOT" 2>/tmp/kanban-cifs-apply.err; then
    echo "remount_ok $MOUNT_ROOT"
    exit 0
  fi
  # remount 失败尝试 umount+mount（fstab 负责源）
  umount "$MOUNT_ROOT" 2>/dev/null || true
fi

if mount "$MOUNT_ROOT" 2>/tmp/kanban-cifs-apply.err; then
  echo "mount_ok $MOUNT_ROOT"
  exit 0
fi

err=$(head -c 200 /tmp/kanban-cifs-apply.err 2>/dev/null || true)
# 凭据已写；挂载失败仍非 0，便于 API 提示人话
echo "凭据已写入，但挂载失败（${err:-未知}）。请确认 BESTEASY 内网、fstab 与共享可达。" >&2
exit 1
