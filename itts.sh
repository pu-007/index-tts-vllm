export ITTS_DIR="/mnt/c/Users/zion/Apps/index-tts-vllm"

function itts {
  local itts_script=("python" "$ITTS_DIR/itts.py")
  local success_keyword="可用的语音角色"
  local max_wait=60 # 启动 Docker 后最大等待时间（秒）
  local sleep_sec=3 # 每次检测间隔

  # 检测服务是否可用
  check_service() {
    if output=$(timeout 5 "${itts_script[@]}" --get-voices 2>&1); then
      echo "$output" | grep -q "$success_keyword"
      return $?
    else
      return 1
    fi
  }

  # 先检测一次
  if check_service; then
    echo "服务已就绪，直接执行命令..."
    "${itts_script[@]}" "$@"
    return 0
  fi

  # API 未启动，立即启动 Docker
  echo "API 未启动，启动 Docker 容器..."
  (cd "$ITTS_DIR" && docker compose up -d)

  # 等待服务初始化完成
  echo "等待服务初始化完成..."
  local ready=0
  for ((i = 0; i < max_wait; i += sleep_sec)); do
    if check_service; then
      ready=1
      break
    fi
    echo "$(date +'%H:%M:%S') - API 仍未就绪，等待 ${sleep_sec}s..."
    sleep $sleep_sec
  done

  if [ $ready -eq 0 ]; then
    echo "服务启动超时，未能检测到关键词 '$success_keyword'"
    return 1
  fi

  echo "服务已就绪，执行命令..."
  "${itts_script[@]}" "$@"
}
