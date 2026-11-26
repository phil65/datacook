Usage
=====

Workflow for data analysis
--------------------------

1.  Import .dat files (File -\> Import -\> From File)

2.  Merge imported datasets if necessary (select datasets -\>
    right-click -\> concat)

3.  Right click resulting dataset -\> Split

4.  Choose split criteria -\> click \"Split\" -\> Click OK. 2 new
    features will get added to the dataset.

5.  Right-click feature \"process_num\" -\> click \"Group by\"

6.  Select processes for data analysis -\> Right-click -\> Click on
    \"Signal analysis\"

7.  Choose feature to analyse for each category and set up the available
    options. Press OK.

    > -   **Reference process**: Process to use for the tolerance band
    > -   **Window size**: Window size of the tolerance band
    > -   **Maximum difference**: Maximum allowed difference for
    >     tolerance band
    > -   **Cons. samples allowed**: used for converter_working.

8.  A new dataset containing the results gets generated.

9.  Export dataset to csv (File -\> Export -\> CSV file)

Implemented score values
------------------------

Flow:

-   **max_flowrate**: Maximum flowrate during process
-   **total_flow**: Integral of flowrate feature
-   **dtw_distance_flow**: DTW distance to reference process

Power:

-   **max_slope_config_1**: Difference to rolling mean (window_size: 25)
-   **time_max_slope_config_1**: Time of max difference
    (window_size: 25)
-   **max_slope_config_2**: Difference to rolling mean (window_size: 45)
-   **time_max_slope_config_2**: Time of max difference
    (window_size: 45)
-   **max_abs_diff_ll**: Maximum absolute difference to lower band
-   **time_max_abs_diff_ll**: Time of maximum absolute difference to
    upper band
-   **max_abs_diff_ul**: Maximum absolute difference to upper band
-   **time_max_abs_diff_ul**: Time of maximum absolute difference to
    upper band
-   **max_rel_diff_ll**: Maximum relative difference to lower band
-   **time_max_rel_diff_ll**: Time of maximum relative difference to
    lower band
-   **max_rel_diff_ul**: Maximum absolute difference to upper band
-   **time_max_rel_diff_ul**: Time of maximum relative difference to
    upper band
-   **max_cons_time_above_ul**: Max consecutive time above lower band
-   **max_cons_time_below_ll**: Max consecutive time below lower band
-   **duration_above_ul**: Total duration above lower band
-   **duration_below_ll**: Total duration below lower band
-   **summed_diffs_to_ll**: Summed difference to lower band
-   **summed_diffs_to_ul**: Summed difference to upper band
-   **max_amplitude**: Maximum amplitude value
-   **time_max_amplitude**: Time of maximum amplitude value
-   **dtw_distance_power**: DTW distance to reference process

Voltage:

-   **converter_working**: voltage does not diverge \> 1% for more than
    0.1s
-   **dtw_distance_voltage**: DTW distance to reference process

Inductor:

-   **max_amplitude**: Maximum amplitude during process
-   **time_max_amplitude**: Point of time when max amplitude is reached

General:

-   **process_duration**: Duration of the process