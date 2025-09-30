import argparse
import random
import sys
import os


def detect_format(lines):
    """
    Detects if the file is in single-line or triple-line format.

    Args:
        lines (list): A list of strings representing the lines of the file.

    Returns:
        str: 'triple' if the file has repeating blocks of three lines,
             'single' otherwise.
    """
    stripped_lines = [line.strip() for line in lines if line.strip()]
    if not stripped_lines:
        return 'single'  # Empty or whitespace-only file

    if len(stripped_lines) % 3 != 0:
        return 'single'

    for i in range(0, len(stripped_lines), 3):
        if not (stripped_lines[i] == stripped_lines[i + 1] ==
                stripped_lines[i + 2]):
            return 'single'

    return 'triple'


def process_file(input_file,
                 output_file=None,
                 operation='shuffle',
                 shuffle=True):
    """
    Processes lines from an input file based on detected format and operation.

    Args:
        input_file (str): Path to the input file.
        output_file (str, optional): Path to the output file. Defaults to None.
        operation (str): 'repeat', 'unrepeat', or 'shuffle'.
        shuffle (bool): Whether to shuffle the lines/groups.
    """
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_file}", file=sys.stderr)
        sys.exit(1)

    file_format = detect_format(lines)

    # Determine the base units for processing
    if file_format == 'triple':
        # For triple format, the unit is the unique line from each group of 3
        units = [line.strip() for line in lines if line.strip()][0::3]
    else:  # 'single'
        # For single format, each line is a unit
        units = [line.strip() for line in lines if line.strip()]

    if shuffle:
        random.shuffle(units)

    output_lines = []

    # Determine the output format based on the operation
    if operation == 'repeat':
        for unit in units:
            for _ in range(3):
                output_lines.append(unit + '\n')
            output_lines.append('...')
    elif operation == 'unrepeat':
        output_lines = [unit + '\n' for unit in units]
    elif operation == 'shuffle':
        if file_format == 'triple':
            for unit in units:
                for _ in range(3):
                    output_lines.append(unit + '\n')
        else:  # 'single'
            output_lines = [unit + '\n' for unit in units]

    # Generate output filename if not provided
    if output_file is None:
        base, ext = os.path.splitext(input_file)

        suffix_parts = []

        # Describe the operation's effect
        if operation == 'shuffle':
            if shuffle:
                suffix_parts.append('shuffled')
        elif operation == 'repeat':
            suffix_parts.append('repeated')
        elif operation == 'unrepeat':
            suffix_parts.append('unrepeated')

        # Add shuffle indicator if it was a modifying operation
        if shuffle and operation in ['repeat', 'unrepeat']:
            suffix_parts.append('shuffled')

        # If no operation and no shuffle, it's a copy
        if not suffix_parts:
            suffix_parts.append('copy')

        output_file = f"{base}_{'_'.join(suffix_parts)}{ext}"

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.writelines(output_lines)
        print(f"Successfully processed file {input_file} to {output_file}.")
    except IOError as e:
        print(f"Error writing to output file {output_file}: {e}",
              file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description=
        "Process text files by shuffling, repeating, or un-repeating lines. "
        "Automatically detects if the input is single-line or triple-line format.",
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-i',
                        '--input',
                        required=True,
                        help="Path to the input text file.")
    parser.add_argument(
        '-o',
        '--output',
        help=
        "Path to the output text file. If not provided, a name will be generated automatically."
    )
    parser.add_argument(
        '--operation',
        choices=['repeat', 'unrepeat', 'shuffle'],
        default='shuffle',
        help=
        ("Specify the operation to perform:\n"
         "'shuffle':  (default) Shuffles lines/groups while preserving the format.\n"
         "'repeat':   Ensures the output is in triple-line format.\n"
         "'unrepeat': Ensures the output is in single-line format."))
    parser.add_argument(
        '--no-shuffle',
        action='store_true',
        help=
        "Disable shuffling. By default, all operations shuffle the content.")

    args = parser.parse_args()

    should_shuffle = not args.no_shuffle

    process_file(args.input, args.output, args.operation, should_shuffle)


if __name__ == "__main__":
    main()
