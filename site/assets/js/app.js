'use strict';

var app = angular.module('dodApp', []);

app.controller({QuizCtrl: [
    '$scope', '$http', '$window',
    function ($scope, $http, $window) {

        $http.post('/quiz')
        .success(function(quiz) {
            $scope.quiz = quiz;
        })
        .error(function(error) {
            console.log(error);
        });
        
        $scope.submit = function(answer) {
            $scope.quiz.answer = answer;
            $http.put('/quiz', $scope.quiz)
            .success(function(quiz) {
                $scope.quiz = quiz;
            })
            .error(function(error) {
                console.log(error);
            });
        };
    }]
});

