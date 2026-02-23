class Opendev < Formula
  desc "Terminal-first AI coding assistant focused on free/community models"
  homepage "https://github.com/selcuksarikoz/opendev"
  version "0.1.5"

  if OS.mac?
    if Hardware::CPU.arm?
      url "https://github.com/selcuksarikoz/opendev/releases/download/v0.1.5/opendev-macos-arm64.tar.gz"
      sha256 "2f94b398eb968bbd0a52ecce28c6ab4049e788345bffc352b3f80c0824ba7bab"
    elsif Hardware::CPU.intel?
      url "https://github.com/selcuksarikoz/opendev/releases/download/v0.1.5/opendev-macos-x86_64.tar.gz"
      sha256 "897a5f53a04e030a227ffc4cb804a02b814033992cda612781ce1633ffcddeab"
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
