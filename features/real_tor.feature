@product @real_tor
Feature: Using the real Tor network
  As a Tails user
  I can connect to the network
  and perform simple operations

  Scenario: Cloning a Git repository anonymously over HTTPS through the real Tor network
    Given I have started Tails from DVD and logged in and the network is connected
    When I clone the Git repository "https://github.com/intrigeri/Dist-Zilla-Plugin-LocaleMsgfmt.git" in GNOME Terminal
    Then the Git repository "Dist-Zilla-Plugin-LocaleMsgfmt" has been cloned successfully
