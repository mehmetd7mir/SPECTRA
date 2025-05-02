//
//  AppCoordinators.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 30.04.2025.
//

import Foundation
import UIKit

class AppCoordinator {
    
    //UINavigationController is a special type of UIViewController.There is a viewControllers : [UIViewController] list in the navigationController.
    //UINavgiationController works like a Screen stack.FiLo.We can push screen(ViewController) and pop.
    //Coordinator manages navigations but it needs to container for the show.(Container -> UINavigationController)
    private var navigationController : UINavigationController
    private var authCoordinator: AuthCoordinator?
    init(navigationController : UINavigationController){
        self.navigationController = navigationController
    }
    
    func start(){
        //if my app is open for the first time.UserDefaults.....(forKey) must be nil.So user has not selected/chosen a language.
        let selectedLanguage = UserDefaults.standard.string(forKey: UserDefaultsKeys.selectedLanguage)
        let shouldRemember = UserDefaults.standard.bool(forKey: UserDefaultsKeys.rememberMe)
        // if selectedLanguage is nil,user have not choose a language
        // I used setViewControllers for the totalt clean up the stack.
        // setViewController takes an array of ViewController and  replaces the current navigation stack with the given ones.
        // {func setViewControllers(_ viewControllers: [UIViewController], animated: Bool)}
        let authCoordinator = AuthCoordinator(navigationController: navigationController)
        if selectedLanguage == nil {
            let languageVC = LanguageSelectionViewController()
            navigationController.setViewControllers([ languageVC ], animated: false)
        } else if shouldRemember {
            authCoordinator.showHome()
        } else {
            authCoordinator.start()
        }

    }
    
}


// MARK: * - * - * -  Things I learned  - * - * - *

/*

editable -->compiled
a.xib ---> a.nib
Genarally xib file is a single page
We should load our xib file to our view.
We call it help of code.

***Bundle.main.loadNibNamed("XView" , owner: self , options : nil)***
 This code load xib file to RAM.(random access memory)
 It is old type.!!!!!
 
 owner : self -> Connect the views to selfClass those are in the "XView"
 
 options : nil -> It waits dictionary but generally we send nil.
 options provides set some special setting while load xib to RAM.
 We can send external objects.For example;
 let externalObjects : [String : Any ] = ["customLabel" : UILabel()]
 let options : [UINib.OptionsKey : Any] = [.externalObjects : externalObjects]
 Bundle.main.loadNibNamed("MyCustomView", owner : self , options : options)
 
 
 ***laodView()***
 Called before viewDidLoad()
 override func loadView(){
    let nib = UINib(nibName : "WelcomeViewController", bundle : nil)
    // we take first view of welcomeviewcontroller with .first and check UIView ? optional and assign to our view of class.
    // instantiate means "somutlaştırmak"
    self.view = nib.instantiate(withOwner: self, options: nil).first as? UIView
 }
 
 if we dont give a nibname and dont override loadView() swift try load from main storyboard(took a error)
 
 */
