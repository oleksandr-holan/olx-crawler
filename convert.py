import os
import re
import sys

from urllib.parse import urlparse, urlunparse

import toml


PIPFILE_TO_UV_DEP_NAMES = {
    "packages": "dependencies",
    "dev-packages": "dev-dependencies",
}


def strip_url_credentials(url: str) -> str:
    """
    Remove username and password from URL if present.
    """
    parsed = urlparse(url)
    # Create new netloc without credentials
    netloc = parsed.hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    # Reconstruct URL without credentials
    clean_url = urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )
    return clean_url


def dump_custom_version(package: str, version: dict) -> str:
    """
    Handle custom version formats (e.g., git, ref, index).
    """
    if "extras" in version:
        extras_str = ",".join(version["extras"])
        package = f"{package}[{extras_str}]"

    if "git" in version:
        git_url = version["git"]
        ref = version.get("ref", "main")
        return f"{package} @ {git_url}@{ref}"

    if "version" in version:
        return f"{package}{version['version']}"

    return package


def convert_pipfile_to_pyproject(
    pipfile_path: str,
    output_path: str,
    project_name: str,
    project_version: str,
    project_description: str,
    python_version: str,
):
    # Load the Pipfile
    with open(pipfile_path) as pipfile:
        pipfile_data = toml.load(pipfile)

    pyproject_data = {
        "project": {
            "name": project_name,
            "version": project_version,
            "description": project_description,
            "requires-python": f"=={python_version}",
            "dependencies": [],
            "dev-dependencies": [],  # tmp for easier map
        },
        "tool": {"uv": {"dev-dependencies": [], "sources": {}}},
    }

    # Handle sources from Pipfile
    if "source" in pipfile_data:
        pyproject_data["tool"]["uv"]["index"] = []
        for source in pipfile_data["source"]:
            # Create source entry with cleaned URL (no credentials)
            source_entry = {
                "name": source["name"].replace("-", "_"),
                "url": strip_url_credentials(source["url"]),
            }
            pyproject_data["tool"]["uv"]["index"].append(source_entry)

    # Track packages with custom index
    packages_with_index = {}

    # Convert dependencies and handle index-specific packages
    for pipfile_name, uv_name in PIPFILE_TO_UV_DEP_NAMES.items():
        if pipfile_name in pipfile_data:
            for package, version in pipfile_data[pipfile_name].items():
                if isinstance(version, str):
                    if version == "*":
                        pyproject_data["project"][uv_name].append(f"{package}")
                    else:
                        pyproject_data["project"][uv_name].append(f"{package}{version}")
                elif isinstance(version, dict):
                    # Check for index specification
                    if "index" in version:
                        packages_with_index[package] = {"index": version["index"]}

                    # Add custom version formats
                    pyproject_data["project"][uv_name].append(
                        dump_custom_version(package, version)
                    )

    # Add packages with custom index to tool.uv.sources
    if packages_with_index:
        for package, index_info in packages_with_index.items():
            index_info["index"] = index_info["index"].replace("-", "_")
            pyproject_data["tool"]["uv"]["sources"][package] = index_info

    # moving dev-dependencies to tool.uv
    pyproject_data["tool"]["uv"]["dev-dependencies"] = pyproject_data["project"].pop(
        "dev-dependencies"
    )

    # Write the pyproject.toml
    with open(output_path, "w") as pyproject_file:
        toml.dump(pyproject_data, pyproject_file)

    transform_file(output_path, output_path)
    print(f"pyproject.toml generated at {output_path}")


def transform_file(input_file, output_file):
    """
    Reads a text file, transforms the specified lines, and writes the updated content to a new file.

    Parameters:
    input_file (str): Path to the input text file.
    output_file (str): Path to the output text file.
    """
    with open(input_file, "r") as file:
        lines = file.readlines()

    transformed_lines = []
    current_section = None

    for line in lines:
        # Check if the line starts with the pattern "[tool.uv.sources."
        match = re.match(r"^\[tool\.uv\.sources\.(.*?)\]$", line.strip())
        if match:
            current_section = match.group(1)
            transformed_lines.append(f"[tool.uv.sources]")
        # Check if the line has the format "index = "<somethingB>""
        elif current_section and line.strip().startswith("index ="):
            index_value = re.search(r'"(.+?)"', line.strip()).group(1)
            transformed_lines.append(f'{current_section} = {{index = "{index_value}"}}')
            current_section = None
        else:
            transformed_lines.append(line.rstrip())

    with open(output_file, "w") as file:
        file.write("\n".join(transformed_lines))

    print(f"Transformation complete. Output file: {output_file}")


def get_input_with_default(prompt, default):
    user_input = input(f"{prompt} [{default}]: ").strip()
    return user_input if user_input else default


def check_existing_pyproject(path):
    if os.path.exists(path):
        print("\n" + "!" * 60)
        print("CRITICAL WARNING:")
        print(f"A pyproject.toml file already exists at {path}")
        print("Running this script will overwrite the existing file.")
        print("!" * 60 + "\n")

        while True:
            response = input("Do you want to proceed? (yes/no): ").lower().strip()
            if response in ["yes", "y"]:
                return True
            elif response in ["no", "n"]:
                return False
            else:
                print("Please answer 'yes' or 'no'.")
    return True


def main():
    print("Welcome to the Pipfile to pyproject.toml converter!")
    print("Please provide the following information:")

    pipfile_path = get_input_with_default("Enter the path to your Pipfile: ", "Pipfile")
    while not os.path.exists(pipfile_path):
        pipfile_path = input(
            "File not found. Please enter a valid path to your Pipfile: "
        ).strip()

    output_path = get_input_with_default(
        "Enter the output path for pyproject.toml", "pyproject.toml"
    )

    if not check_existing_pyproject(output_path):
        print("Operation cancelled. Exiting...")
        sys.exit(0)

    project_name = get_input_with_default("Enter the project name", "project-name")
    project_version = get_input_with_default("Enter the project version", "0.0.0")
    project_description = get_input_with_default(
        "Enter the project description", "Project description"
    )
    python_version = get_input_with_default(
        "Enter the required Python version", "3.10.15"
    )

    convert_pipfile_to_pyproject(
        pipfile_path,
        output_path,
        project_name,
        project_version,
        project_description,
        python_version,
    )


if __name__ == "__main__":
    main()
