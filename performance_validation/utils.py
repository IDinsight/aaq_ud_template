import re
from io import StringIO

import pandas as pd
import yaml


class S3_Handler:
    def __init__(self, s3, s3r, bucket):

        self.s3 = s3
        self.s3r = s3r
        self.bucket = bucket

    def load_yaml(self, prefix, key=None):

        response = self.s3.get_object(Bucket=self.bucket, Key=prefix)

        yaml_config = yaml.safe_load(response["Body"])
        if key is not None:
            yaml_config = yaml_config[key]
        return yaml_config

    def load_dataframe_from_object(self, key):

        data_object = self.s3.get_object(Bucket=self.bucket, Key=key)

        dataframe = pd.read_csv(data_object.get("Body"))

        return dataframe

    def load_dataframe(self, prefix, table=[], token1="", regex=r"."):

        if token1 == "":

            response = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix)

        else:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket, Prefix=prefix, ContinuationToken=token1
            )

        truncboolean = response["IsTruncated"]

        current_table = table.copy()

        if "Contents" not in response:
            raise Exception("No match found for prefix " + prefix)

        for key in response["Contents"]:

            if key["Size"] > 0 and re.match(regex, key["Key"]):

                obj = self.s3r.Object(self.bucket, key["Key"])
                raw_csv = obj.get()["Body"].read().decode("utf-8")
                df = pd.read_csv(StringIO(raw_csv))
                current_table.append(df)
            if truncboolean:
                token = response["NextContinuationToken"]
                self.load_dataframe(prefix, token1=token, table=current_table)

        return pd.concat(current_table, axis=0)
