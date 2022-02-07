###
# This feature relies heavily on the real_tor tag, so let's explain how this works.
#  - the variable @real_tor is set to true if either:
#
#     * the real_tor tag is explicitly used
#     * run_test_suite --disable-chutney is used
#
#    The latter case is probably only useful for development
# - When @real_tor is set, the Test Suite behaves differently, disabling most chutney-related behaviour.

@product @real_tor
Feature: Using Tor bridges and pluggable transports of the real Tor network
  As a Tails user
  I want to circumvent censorship of Tor by using Tor bridges and pluggable transports
  And avoid connecting directly to the Tor Network

  Background:
    Given I have started Tails from DVD without network and logged in
    And I capture all network traffic
    When the network is plugged
    Then the Tor Connection Assistant autostarts

  Scenario: Default, real, Tor bridges
    When I configure the default bridges in the Tor Connection Assistant
    Then Tor is ready
    And Tor is configured to use the default bridges
    And tca.conf includes no bridge
    And available upgrades have been checked
    And Tor is configured to use the default bridges
    And all Internet traffic has only flowed through the default bridges

