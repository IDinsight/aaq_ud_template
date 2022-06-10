import os


class TestNewRuleTool:
    def test_check_new_rule(self, client):
        request_data = {
            "include_keywords": ["Running", "Diving", "swiming"],
            "exclude_keywords": ["Laugh", "Cry"],
            "queries_to_check": [
                "I am cool",
                "I am a laughter inducing maniac.",
                "Life is not about crying, it is about swimming, diving and running.",
                "Let us swim, DIVE, AND RUN",
                "Do you like to run?, ARE you interested in swoming?How about doving?",
            ],
        }

        headers = {"Authorization": "Bearer %s" % os.getenv("UD_INBOUND_CHECK_TOKEN")}

        response = client.post(
            "/tools/check-new-rules", json=request_data, headers=headers
        )
        json_data = response.get_json()

        assert json_data["urgency_scores"] == [0, 0, 0, 1, 1]

    def test_if_rule_overlap_is_detected(self, client):
        request_data = {
            "include_keywords": ["cry", "running"],
            "exclude_keywords": ["disgusting", "parasitic", "love", "run"],
        }

        headers = {"Authorization": "Bearer %s" % os.getenv("UD_INBOUND_CHECK_TOKEN")}

        response = client.post(
            "/tools/validate-rule", json=request_data, headers=headers
        )
        json_data = response.get_json()

        assert json_data["overlapping_include_exclude"] == ["run"]

    def test_if_only_one_keyword_works(self, client):
        request_data = {"include_keywords": ["cry"], "exclude_keywords": []}

        headers = {"Authorization": "Bearer %s" % os.getenv("UD_INBOUND_CHECK_TOKEN")}

        response = client.post(
            "/tools/validate-rule", json=request_data, headers=headers
        )
        json_data = response.get_json()

        assert json_data["ngram_check"] == []

    def test_ngram_check(self, client):
        request_data = {
            "include_keywords": ["angry laughter", "sad baleful trudging"],
            "exclude_keywords": ["does not matter"],
        }

        headers = {"Authorization": "Bearer %s" % os.getenv("UD_INBOUND_CHECK_TOKEN")}

        response = client.post(
            "/tools/validate-rule", json=request_data, headers=headers
        )
        json_data = response.get_json()

        assert json_data["ngram_check"] == ["sad baleful trudging", "does not matter"]

    def test_if_only_stopwords_work(self, client):
        request_data = {"include_keywords": [], "exclude_keywords": ["a"]}

        headers = {"Authorization": "Bearer %s" % os.getenv("UD_INBOUND_CHECK_TOKEN")}

        response = client.post(
            "/tools/validate-rule", json=request_data, headers=headers
        )
        json_data = response.get_json()

        expected_error_msg = ["a"]

        assert json_data["stopword_error"] == expected_error_msg
        assert json_data["no_errors"] == False

    def test_when_no_errors(self, client):
        request_data = {"include_keywords": ["run"], "exclude_keywords": ["swim"]}

        headers = {"Authorization": "Bearer %s" % os.getenv("UD_INBOUND_CHECK_TOKEN")}

        response = client.post(
            "/tools/validate-rule", json=request_data, headers=headers
        )
        json_data = response.get_json()

        assert json_data["no_errors"] == True
