$SETGLOBAL limit 15   * A global parameter defined using $SETGLOB

* A simple GAMS script with $SETGLOB for testing purposes

Sets
    i /1*3/     * Index set for variables and parameters
    ;

* Global parameter
Parameter
    a(i)  Value of parameter for each element in set i /1 10, 2 20, 3 30/
    ;

* Variables
Variables
    x(i)  Decision variables
    z     Objective function
    ;

* Variable declaration
Positive Variable x; * x(i) must be non-negative

* Equations
Equations
    obj  Objective function
    eq1  Example constraint
    ;

* Define the equations
obj.. z =e= sum(i, a(i) * x(i));

eq1.. sum(i, x(i)) =l= %limit%; * Using the global parameter from $SETGLOB

* Model declaration
Model simple_model /all/;

* Solve the model
Solve simple_model using LP minimizing z;

* Display results
Display x.l, z.l;
