import { Component, ElementRef, OnDestroy, OnInit, AfterViewInit, ViewChild, inject, Renderer2 } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

import { Subscription, of } from 'rxjs';
import { switchMap, tap } from 'rxjs/operators';

import { client, WorkbookElementData, WorkbookVariable } from '@sigmacomputing/plugin';

import { SkeletonModule } from 'primeng/skeleton';

import { ConfigService } from '../services/core/config.service';
import { ElementDataService } from '../services/core/element-data.service';
import { VariableService } from '../services/core/variable.service';
import { ActionTriggerService } from '../services/core/action-trigger.service';
import { UiStateService } from '../services/plugin/ui-state.service';
import { SafePipe } from '../pipes/safe.pipe';


@Component({
    selector: 'app-main',
    templateUrl: './main.component.html',
    styleUrls: ['./main.component.css'],
    standalone: true,
    imports: [CommonModule, FormsModule, SkeletonModule, SafePipe]
})

export class MainComponent implements OnInit, AfterViewInit, OnDestroy {

    private subscriptions: Subscription[] = [];

    private elementDataSubscription: Subscription | null = null;

    config: any;
    elementData: WorkbookElementData = {};

    private initialRender: boolean = true;

    // control IDs from config
    private vizUrlControlId: string = '';
    private vizNodeIdControlId: string = '';
    private exploreKeyControlId: string = '';

    // control objects
    private vizUrlControlObject: WorkbookVariable | undefined;

    // control values to use
    vizUrlControlValue: string = '';

    // latest control values from listening to variable changes
    private vizUrlControlValueLatest: string = '';

    vizLoaded: boolean = false;
    private isEventRegistered: boolean = false;
    private variablesListener: (() => void) | undefined;

    constructor(
        private configService: ConfigService,
        private elementDataService: ElementDataService,
        private variableService: VariableService,
        private actionTriggerService: ActionTriggerService,
        private uiStateService: UiStateService,
        private sanitizer: DomSanitizer,
        private renderer2: Renderer2
    ) {}

    async ngOnInit() {

        client.config.configureEditorPanel([
            { type: "action-trigger", name: "onLoadAction", label: "onLoad", },
            { type: "variable", name: "vizUrlControl", label: "URL Control" },
            { type: "variable", name: "vizNodeIdControl", label: "Node ID Control" },
            { type: "variable", name: "exploreKeyControl", label: "Explore Key Control" },
            { type: 'color', name: 'iconColor', label: 'Icon Color' },
        ]);

        this.getConfig();

    }

    ngAfterViewInit() {}

    private getConfig(): void {
        
        // get Sigma config object
        const configSubscription = this.configService.getConfig().subscribe(config => {

            this.config = config;
            
            const iconColor = config.iconColor || '#3d293d';
            document.documentElement.style.setProperty('--p-skeleton-background', iconColor);

            this.vizUrlControlId = config.vizUrlControl;
            this.vizNodeIdControlId = config.vizNodeIdControl;
            this.exploreKeyControlId = config.exploreKeyControl;

            // trigger onLoadAction when the plugin first mounts
            if (this.initialRender) {
                this.triggerOnLoadAction();
                this.initialRender = false;
            }

            // subscribe to variable changes after getting config
            this.subscribeToVariableChanges();

        });

        this.subscriptions.push(configSubscription);
    }

    private triggerOnLoadAction(): void {
        if (this.config?.onLoadAction) {
            this.actionTriggerService.triggerAction(this.config.onLoadAction);
        }
    }

    private parseNodeIdFromUrl(url: string): string {

        // extract the element ID or page ID from the URL path
        // .../workbook/{workbookId}/element/{nodeId}...
        // .../workbook/{workbookId}/page/{nodeId}...
        const elementMatch = url.match(/\/element\/([^\/&\?]+)/);
        const pageMatch = url.match(/\/page\/([^\/&\?]+)/);
        
        if (elementMatch && elementMatch[1]) {
            return elementMatch[1];
        }

        if (pageMatch && pageMatch[1]) {
            return 'pageXX' + pageMatch[1];
        }

        return "";

    };

    private subscribeToVariableChanges(): void {

        if (this.vizUrlControlId) {
            const vizUrlSubscription = this.variableService.getVariable(this.vizUrlControlId).subscribe(value => {
                this.vizUrlControlObject = value;
                this.vizUrlControlValueLatest = (this.vizUrlControlObject?.defaultValue as any)?.value || "";
                
                if (this.vizUrlControlValue !== this.vizUrlControlValueLatest) {
                    this.vizLoaded = false;
                    this.vizUrlControlValue = this.vizUrlControlValueLatest;

                    const nodeId = this.parseNodeIdFromUrl(this.vizUrlControlValue);
                    if (nodeId != '') {
                        this.variableService.setVariable(this.vizNodeIdControlId, nodeId);
                    }
                }
            });
            this.subscriptions.push(vizUrlSubscription);
        }

    }

    registerEvent(): void {

        if (this.isEventRegistered) {
            return;
        }

        this.isEventRegistered = true;

        const dash_iframe = document.getElementById('sigmaViz') as any;
        this.variablesListener = this.renderer2.listen("window", "message", event => {

            if (dash_iframe) {

                if (event.source === dash_iframe.contentWindow && event.data.type.startsWith("workbook:id:onchange")) {
                    this.vizLoaded = true;
                }

                if (event.source === dash_iframe.contentWindow && event.data.type.startsWith("workbook:exploreKey:onchange")) {
                    if (event.data.exploreKey != '') {
                        this.variableService.setVariable(this.exploreKeyControlId, event.data.exploreKey);
                    }
                }

            }

        });

    }

    ngOnDestroy(): void {

        this.isEventRegistered = false;
        if (this.variablesListener) {
            this.variablesListener();
        }

        this.subscriptions.forEach((subscription) => subscription.unsubscribe());
    }

}