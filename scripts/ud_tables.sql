CREATE TABLE urgency_rules (
	urgency_rule_id serial NOT NULL,
	urgency_rule_added_utc timestamp without time zone NOT NULL,
	urgency_rule_author text NOT NULL,
	urgency_rule_title text NOT NULL,
	urgency_rule_tags_include text [] NOT NULL,
	urgency_rule_tags_exclude text [] NOT NULL,
	PRIMARY KEY (urgency_rule_id)
);

CREATE TABLE inbounds_ud (
	inbound_id serial NOT NULL,
	feedback_secret_key text NOT NULL,
	inbound_text text NOT NULL,
	inbound_metadata json,
	inbound_utc timestamp without time zone NOT NULL,
	urgency_score json NOT NULL,
	returned_content json NOT NULL,
	returned_utc timestamp without time zone NOT NULL,
	returned_feedback json,
	PRIMARY KEY (inbound_id)
);
