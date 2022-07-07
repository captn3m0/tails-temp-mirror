@product
Feature: Using Snowflake bridges
  As a Tails user
  I want easy circumvention of censorship of Tor through Snowflake

  Background:
    Given I have started Tails from DVD without network and logged in
    And I capture all network traffic
    # Right now, snowflake can only be tested using the real Tor.
    # this workaround is similar to using --disable-chutney (except chutney still runs)
    And I reconfigure the host to use the real Tor
    When the network is plugged
    Then the Tor Connection Assistant autostarts

  @supports_real_tor
  Scenario: Snowflake
    When I configure some snowflake bridges in the Tor Connection Assistant in easy mode
    Then I wait until Tor is ready
    And tca.conf includes the configured bridges
    And available upgrades have been checked
    And OnionCircuits only show snowflake bridges
    And all Internet traffic has only flowed through snowflake or connectivity check service
