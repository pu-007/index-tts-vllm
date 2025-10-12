#!/usr/bin/env python3
import argparse
import requests
import json
import sys
from datetime import datetime
import os
import logging
import shutil
import subprocess
import termios
import tty
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

DEBUG = False

# 配置日志以帮助调试
logging.basicConfig(level=logging.DEBUG if DEBUG else logging.ERROR,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def getch():
    """Gets a single character from standard input."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
        if ch == '\x03':  # Handle Ctrl+C
            raise KeyboardInterrupt
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def get_available_voices(api_url="http://localhost:8001/audio/voices"):
    """获取可用的语音角色列表"""
    try:
        logger.debug(f"获取语音角色，API地址: {api_url}")
        response = requests.get(api_url)
        response.raise_for_status()
        logger.debug(f"获取语音角色响应状态码: {response.status_code}")
        voices_data = response.json()
        return list(voices_data.keys())
    except requests.exceptions.RequestException as e:
        print(f"获取语音角色失败: {str(e)}", file=sys.stderr)
        logger.error(f"获取语音角色失败: {str(e)}")
        sys.exit(1)


def read_file_content(file_path):
    """读取文件内容"""
    if not os.path.exists(file_path):
        print(f"错误: 文件 '{file_path}' 不存在", file=sys.stderr)
        sys.exit(1)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except IOError as e:
        print(f"读取文件失败: {str(e)}", file=sys.stderr)
        sys.exit(1)


def process_text_content(input_text, shuffle=False, repeat=False):
    """根据选项处理文本内容（打乱顺序/重复）"""
    if not shuffle and not repeat:
        return input_text

    lines = [
        line.strip() for line in input_text.strip().split('\n')
        if line.strip()
    ]

    if shuffle:
        random.shuffle(lines)

    if repeat:
        repeated_lines = []
        for line in lines:
            repeated_lines.extend([line, line, line, '...'])
        lines = repeated_lines

    return '\n'.join(lines)


def generate_default_output_filename(voice, input_filename=None):
    """生成默认的输出文件名"""
    now = datetime.now()
    timestamp = f"{now.month:02d}{now.day:02d}-{now.hour:02d}{now.minute:02d}{now.second:02d}"
    if input_filename:
        base_name = os.path.splitext(os.path.basename(input_filename))[0]
        return f"{voice}-{base_name}-{timestamp}.mp3"
    return f"{voice}-{timestamp}.mp3"


def compress_audio(file_path):
    """使用ffmpeg压缩音频文件"""
    if not shutil.which('ffmpeg'):
        print("\n警告: 'ffmpeg' 未安装或不在系统 PATH 中。跳过音频压缩。", file=sys.stderr)
        return

    temp_output = f"{os.path.splitext(file_path)[0]}_compressed.mp3"
    command = [
        'ffmpeg', '-i', file_path, '-y', '-ar', '32000', '-b:a', '48k', '-ac',
        '1', temp_output
    ]

    try:
        original_size = os.path.getsize(file_path)
        print(f"\n正在压缩音频: {os.path.basename(file_path)}...")
        subprocess.run(command,
                       check=True,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        compressed_size = os.path.getsize(temp_output)
        shutil.move(temp_output, file_path)
        print(
            f"压缩成功: {os.path.basename(file_path)} "
            f"({original_size / 1024:.1f} KB -> {compressed_size / 1024:.1f} KB)"
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"音频压缩失败: {e}", file=sys.stderr)
        if os.path.exists(temp_output):
            os.remove(temp_output)


def play_audio_interactive(file_path):
    """使用mpv播放音频并提供交互式控制（简化版，无保存）"""
    if not sys.stdin.isatty():
        play_audio(file_path)
        return

    try:
        subprocess.run(['mpv', '--version'], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("\n错误: 播放功能需要 'mpv'。请安装 mpv。", file=sys.stderr)
        return

    mpv_process = None
    try:
        command = ['mpv', '--no-video', '--really-quiet', file_path]
        mpv_process = subprocess.Popen(command)

        print("\n--- 交互式播放 ---")
        print(f"正在播放: {os.path.basename(file_path)}")
        print("按 [q] 退出, [r] 重播, [p] 暂停/播放。")
        print("--------------------")

        # This is a simplified wait loop; for a real CLI you might use a more robust method.
        mpv_process.wait()

    except Exception as e:
        print(f"\n播放时发生错误: {e}", file=sys.stderr)
    finally:
        if mpv_process and mpv_process.poll() is None:
            mpv_process.terminate()


def play_audio(file_path):
    """使用mpv播放音频文件（非交互式）"""
    try:
        subprocess.run(['mpv', '--version'], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("\n错误: 播放功能需要 'mpv'。请安装 mpv。", file=sys.stderr)
        return

    try:
        print(f"正在播放: {os.path.basename(file_path)}... (按 Ctrl+C 停止)")
        subprocess.run(['mpv', '--no-video', file_path],
                       check=True,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except KeyboardInterrupt:
        print("\n播放已停止。")
    except subprocess.CalledProcessError as e:
        print(f"使用 mpv 播放失败: {e}", file=sys.stderr)


def text_to_speech(model,
                   voice,
                   input_text,
                   output_file,
                   api_url="http://localhost:8001/audio/speech"):
    """调用TTS API将文本转换为语音"""
    payload = {"model": model, "input": input_text, "voice": voice}
    try:
        logger.debug(f"发送TTS请求到: {api_url} (角色: {voice})")
        response = requests.post(
            api_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            stream=True)
        response.raise_for_status()

        with open(output_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return True, f"语音生成成功: {os.path.abspath(output_file)}"
    except requests.exceptions.RequestException as e:
        error_message = f"语音生成失败 (角色: {voice}): {e}"
        if 'response' in locals() and hasattr(response, 'text'):
            try:
                error_message += f"\n服务器错误: {response.text}"
            except Exception as E:
                logger.error(f"无法获取服务器响应文本: {E}")
        return False, error_message


def main():
    parser = argparse.ArgumentParser(
        description='TTS文本转语音命令行工具',
        formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('input_text', nargs='?', default=None, help='输入文本内容')
    parser.add_argument('--get-voices',
                        action='store_true',
                        help='获取所有可用的语音角色并退出')
    parser.add_argument('-m',
                        '--model',
                        default='kusuriuri/IndexTTS-1.5-vLLM',
                        help='使用的TTS模型 (默认: %(default)s)')
    parser.add_argument('-v',
                        '--voice',
                        default='pu',
                        help='使用的语音角色, 可用逗号分隔指定多个 (例如: pu,cat,candy)')
    parser.add_argument('-f', '--input-file', nargs='+', help='从一个或多个文件读取输入文本')
    parser.add_argument('-o',
                        '--output',
                        help='输出音频文件路径 (默认: 角色-输入文件名-时间.mp3)\n'
                        '如果指定了多个任务，文件名会自动附加角色和输入文件名。')
    parser.add_argument('-u',
                        '--api-url',
                        default="http://localhost:8001/audio/speech",
                        help='TTS服务的API地址 (默认: %(default)s)')
    parser.add_argument('--stdin', action='store_true', help='从标准输入读取文本')
    parser.add_argument('--play',
                        action='store_true',
                        help='生成后自动播放音频 (需要安装 mpv)')
    parser.add_argument('--no-compress',
                        action='store_true',
                        help='禁用音频压缩 (默认使用ffmpeg压缩)')
    parser.add_argument('--shuffle-text',
                        action='store_true',
                        help='为每个声音随机打乱文本行的顺序')
    parser.add_argument('--repeat-text',
                        action='store_true',
                        help='将文本中的每一行重复三遍')
    parser.add_argument('--concurrency',
                        type=int,
                        default=2,
                        help='同时处理的并发请求数 (默认: %(default)s)')

    args = parser.parse_args()

    if args.get_voices:
        from urllib.parse import urlparse, urlunparse
        parsed_url = urlparse(args.api_url)
        # Assuming the base URL structure is http://host:port/
        voices_url = urlunparse(parsed_url._replace(path='/audio/voices'))
        voices = get_available_voices(voices_url)
        print("可用的语音角色:")
        for voice in voices:
            print(f"  - {voice}")
        return

    # If we are not getting voices, we must have some input text.
    # 1. Get inputs (list of dicts with 'filename' and 'content')
    inputs = []
    # Priority: input_file > input_text > stdin
    if args.input_file:
        for file_path in args.input_file:
            content = read_file_content(file_path)
            if content:
                inputs.append({'filename': file_path, 'content': content})
    else:
        input_text = None
        if args.input_text is not None:
            input_text = args.input_text
        elif args.stdin or not sys.stdin.isatty():
            input_text = sys.stdin.read()
        else:
            # No positional arg, no file, not piped. This is an error.
            parser.print_help(sys.stderr)
            print("\n错误: 没有提供输入文本。", file=sys.stderr)
            print("请提供文本作为参数, 或使用 --input-file, 或通过管道/--stdin 传入。",
                  file=sys.stderr)
            sys.exit(1)

        if not input_text or not input_text.strip():
            print("错误: 输入文本为空。", file=sys.stderr)
            sys.exit(1)
        inputs.append({'filename': None, 'content': input_text})

    # 2. Get voices
    voices = [v.strip() for v in args.voice.split(',') if v.strip()]

    # 3. Create generation tasks
    tasks = []
    total_tasks = len(voices) * len(inputs)

    for voice in voices:
        for input_item in inputs:
            processed_text = process_text_content(input_item['content'],
                                                  args.shuffle_text,
                                                  args.repeat_text)
            if not processed_text:
                print(
                    f"警告: 处理后文本为空，跳过任务 (角色: {voice}, 输入: {input_item['filename'] or 'stdin/arg'})",
                    file=sys.stderr)
                continue

            input_filename_for_naming = input_item['filename']
            if args.output:
                base, ext = os.path.splitext(args.output)
                if total_tasks > 1:
                    input_name_part = ""
                    if input_filename_for_naming:
                        input_name_part = f"-{os.path.splitext(os.path.basename(input_filename_for_naming))[0]}"
                    output_file = f"{base}-{voice}{input_name_part}{ext or '.mp3'}"
                else:
                    output_file = args.output
            else:
                output_file = generate_default_output_filename(
                    voice, input_filename_for_naming)

            tasks.append({
                'model': args.model,
                'voice': voice,
                'input_text': processed_text,
                'output_file': output_file,
                'api_url': args.api_url
            })

    if not tasks:
        print("没有要执行的任务。", file=sys.stderr)
        sys.exit(0)

    # 4. Execute tasks concurrently
    generated_files = []
    print(f"总共 {len(tasks)} 个任务，使用 {args.concurrency} 个并发进行处理...")

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        future_to_task = {
            executor.submit(text_to_speech, **task): task
            for task in tasks
        }

        for i, future in enumerate(as_completed(future_to_task)):
            task = future_to_task[future]
            output_file = task['output_file']
            print(f"({i+1}/{len(tasks)}) ", end="")
            try:
                success, message = future.result()
                if success:
                    print(message)
                    generated_files.append(output_file)
                    if not args.no_compress:
                        compress_audio(output_file)
                else:
                    print(message, file=sys.stderr)
            except Exception as exc:
                print(f"任务 {os.path.basename(output_file)} 执行时发生意外错误: {exc}",
                      file=sys.stderr)

    # 5. Play generated audio
    if args.play and generated_files:
        print("\n--- 开始播放生成的音频 ---")
        if len(generated_files) == 1:
            play_audio_interactive(generated_files[0])
        else:
            for i, file_path in enumerate(generated_files):
                print(f"\n({i+1}/{len(generated_files)}) ", end="")
                play_audio(file_path)
        print("\n--- 所有音频播放完毕 ---")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n程序已退出。")
        sys.exit(0)
