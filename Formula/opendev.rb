class Opendev < Formula
  desc "Terminal-first AI coding assistant focused on free/community models"
  homepage "https://github.com/selcuksarikoz/opendev"
  version "0.0.2"

  if OS.mac?
    if Hardware::CPU.arm?
      url "https://github.com/selcuksarikoz/opendev/releases/download/v0.0.2/opendev-macos-arm64.tar.gz"
      sha256 "ca6daa15b5c70e288dd6479bfdc6a803bf77ce214542b12bb4e9b2ed53223f94"
    elsif Hardware::CPU.intel?
      url "https://github.com/selcuksarikoz/opendev/releases/download/v0.0.2/opendev-macos-x86_64.tar.gz"
      sha256 "11b545d2bdcaa337a58a4fdd4b27e511442ecd2db751e19fbdd97c5f8cb1f02f"
    else
      odie "Unsupported macOS CPU."
    end
  else
    odie "Homebrew formula currently ships macOS binaries only."
  end

  def install
    bin.install "opendev"
  end

  test do
    assert_match "usage", shell_output("#{bin}/opendev --help 2>&1").downcase
  end
end
