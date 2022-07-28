July 28, 2022

CURRENT VERSION: aaq_ud_template:v1.0.0

# API Instructions for AAQ Urgency Detection App (Template)

Requests to all the endpoints below (except `/healthcheck`) must be authenticated with the bearer token in the header.
This bearer token must be the same as the environment variable `UD_INBOUND_CHECK_TOKEN`.

### Check if an inbound message is urgent: `POST /inbound/check`

#### Params

|Param|Type|Description|
|---|---|---|
|`text_to_match`|required, string| The text to be checked for urgency|
|`metadata`|optional, can be list/dict/string/etc.|Any custom metadata (inbound phone number/hash, labels, etc.). This will be stored in the inbound query database.|

##### Example

```json
{
  "text_to_match": "I like to hike rocks by the lake",
  "metadata": {
    "phone_number": "+12125551234",
    "joke": "what did the fish say"
  }
}
```

#### Response

|Param|Type|Description|
|---|---|---|
|`urgency_score`|float between 0.0 and 1.0|Urgency score of the message, 1.0 indicating highest urgency and 0.0 indicating not urgent.|
|`matched_urgency_rules`|list of dicts|Each dict describes the urgency rule that was matched. Its contents are: <br><ul><li><code>rule_id</code>: urgency rule ID in the DB table </li><li><code>title</code>: urgency rule title in the DB table</li><li><code>include</code>: list of include keywords</li><li><code>exclude</code>: list of exclude keywords</li></ul>See below for an example response.|
|`inbound_id`|integer|ID of inbound query, to be used when submitting feedback|
|`feedback_secret_key`|string|Secret key attached to inbound query, to be used when submitting feedback|

##### Example

```json
{
  "urgency_score": 1.0,
  "matched_urgency_rules": [
    {
      "rule_id": 1,
      "title": "hiking",
      "include": ["rock", "lake", "hike"],
      "exclude": []
    },
    {
      "rule_id": 2,
      "title": "no_love",
      "include": [],
      "exclude": ["love"]
    }
  ],
  "feedback_secret_key": "abcde12345",
  "inbound_id": 123
}
```

### Insert feedback for an inbound message: `PUT /inbound/feedback`

Use this endpoint to append feedback to an inbound message. You can continuously append feedback via this endpoint. All
existing feedback will be saved.

#### Params

|Param|Type|Description|
|---|---|---|
|`inbound_id`|required, int|Provided in response to original /inbound/check POST.|
|`feedback_secret_key`|required, string|Provided in response to original /inbound/check POST.|
|`feedback`|optional, any format|Any custom feedback. Directly saved by us.|

#### Response

Response is one of the following pairs of (message, HTTP status)

* `"Success", 200`: Successfully added feedback
* `"No Matches", 404`: Did not match any previous inbound query by `inbound_id`
* `"Incorrect Feedback Secret Key", 403`: Matched previous inbound query by `inbound_id`, but `feedback_secret_key` is incorrect

### Check new urgency rule: `POST /tools/check-new-rules`
⚠️ This endpoint is disabled when `DEPLOYMENT_ENV=PRODUCTION`.

The model will check each query message against the new urgency rule (defined by `include_keywords`
and `exclude_keywords`), and returns the preprocessed forms of all inputs as well as whether each message is urgent or
not according to this new rule.

This endpoint is used by the demo (admin) app's "Check New Urgency Rule" tool.

#### Params

|Param|Type|Description|
|---|---|---|
|`include_keywords`|required, list[str]|Keywords that must be present -- in un-preprocessed form|
|`exclude_keywords`|required, list[str]|Keywords that must not be present -- in un-preprocessed form|
|`queries_to_check`|required, list[str]|A list of text messages to match|

##### Example

```json
{
  "include_keywords": ["Running","Diving","swiming"],
  "exclude_keywords": ["Laugh","Cry"],
  "queries_to_check": [
    "I am cool",
    "Do you like to run?, ARE you interested in swoming?How about doving?"
  ]
}
```

#### Response

|Param|Type|Description|
|---|---|---|
|`preprocessed_include_kws`|list|preprocessed versions of `include_keywords`|
|`preprocessed_exclude_kws`|list|preprocessed versions of `exclude_keywords`|
|`preprocessed_queries`|list of lists|preprocessed versions of `queries_to_check`|
|`urgency_scores`|list of floats|each score corresponds to the urgency score for each message in `queries_to_check`. 1.0 means urgent, 0.0 means not urgent.|

##### Example
```json
{
  "preprocessed_include_kws": ["run", "dive", "swim"],
  "preprocessed_exclude_kws": ["laugh", "cri"],
  "preprocessed_queries": [
    ["cool"],
    ["like", "run", "interest", "in", "swim", "how", "dive", "like_run", "run_interest", "interest_in", "in_swim", "swim_how", "how_dive"]
  ],
  "urgency_scores": [0.0, 1.0] 
}
```

### Check if an urgency rule is valid: `POST /tools/validate-rule`
⚠️ This endpoint is disabled when `DEPLOYMENT_ENV=PRODUCTION`.

#### Params

|Param|Type|Description|
|---|---|---|
|`include_keywords`|required, list[str]|Keywords that must be present -- in un-preprocessed form|
|`exclude_keywords`|required, list[str]|Keywords that must not be present -- in un-preprocessed form|

#### Response

|Param|Type|Description|
|---|---|---|
|`no_errors`|bool|True if the rule is valid.|
|`stopword_error`|list or null|list of keywords that become empty string after preprocessing. `null` if not applicable.|
|`overlapping_include_exclude`|list or null|list of keywords that are both in `include_keywords` and `exclude_keywords`. `null` if not applicable|
|`ngram_check`|list or null|list of keywords that don't fit into the ngram range defined in `config/parameters.yml`. `null` if not applicable.|

### Refresh urgency rules from database: `GET /internal/refresh-rules`

Used internally by the core app to re-load FAQs from database.

### Healthcheck: `GET /healthcheck`

Checks for connection to DB.

No authentication is required for this endpoint.

### Authenticated healthcheck: `GET /auth-healthcheck`

Same as `GET /healthcheck` but requires authentication.
