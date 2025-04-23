import os
import json
import numpy as np
import pandas as pd

report_name = os.environ["REPORT_NAME"]


def extract_column_value_from_llm(data):
    llm_output = []

    for table_entity in data["extractedTagValues"]["TableEntities"]:
        for row in table_entity["PredictedRows"]:
            for column in row["PredictedColumns"]:
                if column["ColumnKey"] == "tag_IT_applications_tbl_applicationName":
                    llm_output.append(column["ColumnValue"])

    return llm_output


def extract_column_value_from_report(df):
    report_output = []

    for item in df["IT applications, IT processes and ITGCs"].to_list()[3:]:
        if item == "Insert additional rows as needed":
            break
        report_output.append(item)

    return report_output


if __name__ == "__main__":
    # List all the reports in the data/reports folder having file extension .xlsx

    cummulative_output = {
        "report_name": [],
        "report_output": [],
        "llm_output": [],
        "is_carved_out": [],
    }

    for report_file_name in os.listdir("data/reports"):
        if report_file_name.endswith(".xlsx"):
            report_name = os.path.splitext(report_file_name)[0]

            cummulative_output["report_name"].append(report_name)

            output_folder = os.path.join("data", "reports")
            file_name = f"{report_name}.xlsx"
            file_path = os.path.join(output_folder, file_name)
            df = pd.read_excel(file_path, sheet_name="IT apps, IT processes & ITGCs")

            report_output = extract_column_value_from_report(df)
            cummulative_output["report_output"].append(report_output)

            output_folder = os.path.join("data", "output")
            file_name = f"{report_name}-it-apps.txt"
            file_path = os.path.join(output_folder, file_name)

            with open(file_path, "r") as f:
                data = json.load(f)

                llm_ouput = extract_column_value_from_llm(data)
                cummulative_output["llm_output"].append(llm_ouput)

            if len(report_output) == 0:
                cummulative_output["is_carved_out"].append(True)
            else:
                cummulative_output["is_carved_out"].append(False)

    # Report coverage in percentage:
    # Scan through each item in report_output and if it exists in llm_ouput,
    # increment the count. Finally, divide the count by the total number of items
    # in report_output and multiply by 100 to get the percentage coverage.

    # Report hallunication in percentage:
    # Scan through each item in llm_ouput and if it does not exist in report_output,
    # increment the count. Finally, divide the count by the total number of items
    # in llm_ouput and multiply by 100 to get the percentage hallunication.

    header = "Report Name    |    Coverage    |    Hallucination"
    print("-" * len(header))
    print(header)
    print("-" * len(header))

    avg_cov = []
    avg_hall = []

    for i, report_name in enumerate(cummulative_output["report_name"]):
        local_report_output = cummulative_output["report_output"][i]
        local_llm_ouput = cummulative_output["llm_output"][i]

        # print(f"{report_name} | {local_report_output} | {local_llm_ouput}")

        # Coverage
        if len(local_report_output) == 0:
            coverage = "N/A (Carved out)"
        else:
            count = 0

            for item in local_report_output:
                if item in local_llm_ouput:
                    count += 1

            coverage = count / len(local_report_output)
            avg_cov.append(coverage)

            coverage = f"{coverage * 100}%"

        # Hallunication
        if len(local_llm_ouput) == 0:
            hallunication = "Nil"
        else:
            count = 0

            for item in local_llm_ouput:
                if item not in local_report_output:
                    count += 1

            hallunication = count / len(local_llm_ouput)
            avg_hall.append(hallunication)

            hallunication = f"{hallunication * 100}%"

        print(f"{report_name} | {coverage} | {hallunication}")

    print("-" * len(header))
    print(f"Average | {np.mean(avg_cov) * 100}% | {np.mean(avg_hall) * 100}%")
    print("-" * len(header))
