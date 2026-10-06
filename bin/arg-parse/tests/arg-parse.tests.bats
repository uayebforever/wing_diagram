bats_require_minimum_version 1.5.0

function print_output() {

        echo "---command output---"
        if [[ "${#output_lines[@]}" -ne 0 ]]; then
            for line in "${output_lines[@]}"; do
                echo "$line"
            done
        fi
        echo "--- error ----------"
        if [[ "${#stderr_lines[@]}" -ne 0 ]]; then
            for line in "${stderr_lines[@]}"; do
                echo "$line"
            done
        fi
        echo "--------------------"

}

@test "Value argument" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ../arg-parse.sh name= -- --name=Charlie

    print_output

    [ $status -eq 0 ]
    [ "$output" == "name=\"Charlie\"; " ]

}

@test "Value argument with numbers in name" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ../arg-parse.sh name2= -- --name2=Charlie

    print_output

    [ $status -eq 0 ]
    [ "$output" == "name2=\"Charlie\"; " ]

}

@test "Value argument with dash in name" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ../arg-parse.sh name-for= -- --name-for=Charlie

    print_output

    [ $status -eq 0 ]
    [ "$output" == "name_for=\"Charlie\"; " ]

}

@test "Value argument incorrectly not given a value" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ../arg-parse.sh name= -- --name

    print_output

    [ $status -ne 0 ]
    [ "$stderr" == "Argument error: --name requires a value, like \"--name=foobar\"" ]

}

@test "Missing a required value argument" {
    skip "Feature not yet available."

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ../arg-parse.sh name= greeting= -- --name=Charlie

    print_output

    [ $status -ne 0 ]
    [ "$stderr" == "Argument error: required argument --greeting=<value> missing." ]

}

@test "Flag argument" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ../arg-parse.sh flag -- --flag

    print_output

    [ $status -eq 0 ]
    [ "$output" == "flag=\"true\"; " ]

}

@test "Flag argument negated" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ../arg-parse.sh flag -- --flag --no-flag

    print_output

    [ $status -eq 0 ]
    [ "$output" == "flag=\"true\"; flag=\"false\"; " ]

}

@test "Flag argument with numbers in name" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ../arg-parse.sh name2 -- --name2

    print_output

    [ $status -eq 0 ]
    [ "$output" == "name2=\"true\"; " ]

}

@test "Flag argument with dash in name" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ../arg-parse.sh flag-name -- --flag-name

    print_output

    [ $status -eq 0 ]
    [ "$output" == "flag_name=\"true\"; " ]

}

@test "Flag argument incorrectly given a value" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ../arg-parse.sh flag -- --flag=blah

    print_output

    [ $status -ne 0 ]
    [ "$stderr" == "Argument error: --flag does not accept a value" ]

}

@test "Undefined argument given" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ../arg-parse.sh flag -- --unexpected=blah

    print_output

    [ $status -ne 0 ]
    [ "$stderr" == "Unexpected argument: --unexpected=blah" ]

}

@test "Multiple arguments" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ../arg-parse.sh flag name= greeting= -- --name=Charlie --greeting=Hi --flag

    print_output

    [ $status -eq 0 ]
    [ "$output" == "name=\"Charlie\"; greeting=\"Hi\"; flag=\"true\"; " ]

}

@test "Multiple arguments, different order" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ../arg-parse.sh flag name= greeting= -- --greeting=Hi --flag --name=Charlie

    print_output

    [ $status -eq 0 ]
    [ "$output" == "greeting=\"Hi\"; flag=\"true\"; name=\"Charlie\"; " ]

}

@test "Invalid argument definition" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ../arg-parse.sh bad\$arg= --

    print_output

    [ $status -ne 0 ]
    [ "$stderr" == 'arg-parse.sh error: invalid argument definition given: bad$arg=' ]

}

@test "E2E: Hello world" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ./arg-parse-hello-world.sh --greeting=Hello --name=Charlie

    print_output

    [ $status -eq 0 ]
    [ "$output" == "Hello, Charlie" ]
}


@test "E2E: Hello world with flag" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ./arg-parse-hello-world.sh --greeting=Hello --name=Charlie --bang

    print_output

    [ $status -eq 0 ]
    [ "$output" == "Hello, Charlie!" ]

}

@test "E2E: Hello world defaults" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ./arg-parse-hello-world.sh

    print_output

    [ $status -eq 0 ]
    [[ "$output" == "Hello, World" ]] || false

}
@test "E2E: Hello world usage on error" {

    cd $BATS_TEST_DIRNAME

    run --separate-stderr ./arg-parse-hello-world.sh --greeting --name=Charlie --bang

    print_output

    [ $status -ne 0 ]
    [[ "$stderr" == *"Usage: arg-parse-hello-world.sh"* ]] || false
    [[ "$stderr" != *"Arguments sdf parsed"* ]] || false

}
